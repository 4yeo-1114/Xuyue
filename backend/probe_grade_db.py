# -*- coding: utf-8 -*-
"""临时探针：连接同事的 PG 题库，列出表与关键表结构。用完即删。"""
import psycopg2

HOST = "192.168.1.199"
PORT = 5432
USER = "postgres"
PASSWORD = "postgres"
DB = "grade"

try:
    c = psycopg2.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, dbname=DB, connect_timeout=6)
    cur = c.cursor()
    cur.execute("select current_database(), current_user")
    print("CONNECTED:", cur.fetchone())
    cur.execute(
        "select table_schema, table_name from information_schema.tables "
        "where table_schema not in ('pg_catalog','information_schema') "
        "order by table_schema, table_name"
    )
    rows = cur.fetchall()
    print("TABLES (%d):" % len(rows))
    for s, t in rows:
        print("   ", s, ".", t)
    c.close()
except Exception as e:
    print("FAIL:", repr(str(e))[:400])
