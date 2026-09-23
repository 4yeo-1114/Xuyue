"""学分银行核心：账户懒初始化、积分变动（同事务写流水 + 更新账户）。

所有积分变动必须走本模块，保证 balance_after 与 credit_accounts.balance 一致。
扣减不允许负余额；扣减/兑换场景由调用方先 SELECT ... FOR UPDATE 锁行。
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.credit_account import CreditAccount
from app.models.credit_transaction import CreditTransaction


def ensure_credit_account(db: Session, student_id: str) -> CreditAccount:
    """懒初始化积分账户（初始余额 0）。返回账户对象（未 commit，随外层事务提交）。"""
    account = db.query(CreditAccount).filter(CreditAccount.student_id == student_id).first()
    if account is None:
        account = CreditAccount(student_id=student_id)
        db.add(account)
        db.flush()
    return account


def get_locked_account(db: Session, student_id: str) -> CreditAccount:
    """SELECT ... FOR UPDATE 锁行获取账户（并发下防止超扣/超发）。不存在则懒创建。"""
    account = (
        db.query(CreditAccount)
        .filter(CreditAccount.student_id == student_id)
        .with_for_update()
        .first()
    )
    if account is None:
        account = CreditAccount(student_id=student_id)
        db.add(account)
        db.flush()
    return account


def apply_credit_to_account(
    db: Session,
    account: CreditAccount,
    class_id: str,
    amount: int,
    transaction_type: str,
    operator_id: str,
    description: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
) -> CreditTransaction:
    """在已锁定/已获取的账户上应用积分变动并写流水。返回 txn，未 commit。

    - amount > 0 入账（total_earned += amount）；amount < 0 扣减（total_spent += |amount|）
    - 扣减后余额不允许为负（返回 400 insufficient_balance）
    """
    if amount == 0:
        raise HTTPException(status_code=400, detail="积分变动金额不能为 0")
    new_balance = (account.balance or 0) + amount
    if new_balance < 0:
        raise HTTPException(status_code=400, detail="insufficient_balance：积分不足，无法扣减")

    account.balance = new_balance
    if amount > 0:
        account.total_earned = (account.total_earned or 0) + amount
    else:
        account.total_spent = (account.total_spent or 0) + (-amount)

    txn = CreditTransaction(
        student_id=account.student_id,
        class_id=class_id,
        amount=amount,
        transaction_type=transaction_type,
        balance_after=new_balance,
        source_type=source_type,
        source_id=source_id,
        operator_id=operator_id,
        description=description,
    )
    db.add(txn)
    db.flush()
    return txn


def apply_credit_change(
    db: Session,
    student_id: str,
    class_id: str,
    amount: int,
    transaction_type: str,
    operator_id: str,
    description: Optional[str] = None,
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    lock: bool = True,
) -> tuple[CreditAccount, CreditTransaction]:
    """在同一事务内更新积分账户并写入积分流水（账户行 SELECT FOR UPDATE 加锁）。

    - amount > 0 入账（total_earned += amount）；amount < 0 扣减（total_spent += |amount|）
    - 扣减后余额不允许为负（返回 400 insufficient_balance）
    - 返回 (account, transaction)，未 commit，随外层事务一并提交
    """
    account = get_locked_account(db, student_id) if lock else ensure_credit_account(db, student_id)
    txn = apply_credit_to_account(
        db, account, class_id, amount, transaction_type, operator_id,
        description=description, source_type=source_type, source_id=source_id,
    )
    return account, txn


def reconcile_account(db: Session, student_id: str) -> dict:
    """对账单个学生：SUM(amount) 与 account.balance / 最近一条 balance_after 对比。"""
    from sqlalchemy import func as sa_func

    account = db.query(CreditAccount).filter(CreditAccount.student_id == student_id).first()
    if account is None:
        return {"studentId": student_id, "accountExists": False, "status": "no_account",
                "sumAmount": 0, "accountBalance": 0, "lastBalanceAfter": None}

    row = (
        db.query(sa_func.sum(CreditTransaction.amount))
        .filter(CreditTransaction.student_id == student_id)
        .scalar()
    )
    sum_amount = row if row is not None else 0
    last_txn = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.student_id == student_id)
        .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
        .first()
    )
    last_balance_after = last_txn.balance_after if last_txn else None
    ok = int(sum_amount) == int(account.balance or 0)
    if ok and last_balance_after is not None:
        ok = int(last_balance_after) == int(account.balance or 0)
    return {
        "studentId": student_id,
        "accountExists": True,
        "status": "ok" if ok else "mismatch",
        "sumAmount": int(sum_amount),
        "accountBalance": int(account.balance or 0),
        "lastBalanceAfter": last_balance_after,
    }
