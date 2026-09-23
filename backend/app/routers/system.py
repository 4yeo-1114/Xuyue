from fastapi import APIRouter, Depends

from app.dependencies import get_current_user_id
from app.grading.storage_cleanup import run_grading_data_cleanup
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/system", tags=["system"])


@router.post("/cleanup-grading-data", response_model=ApiResponse[dict])
def cleanup_grading_data(user_id: str = Depends(get_current_user_id)):
    """清理当前用户 grading_data_{user_id} 中无用临时文件、孤儿留痕图等。"""
    return ApiResponse(data=run_grading_data_cleanup(user_id))
