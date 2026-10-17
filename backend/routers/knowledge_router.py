"""知识点管理路由"""
import json
from fastapi import APIRouter
from schemas import APIResponse
from config import KNOWLEDGE_TAGS_PATH

router = APIRouter()

@router.get("/tags", response_model=APIResponse)
async def get_knowledge_tags():
    """获取所有知识点标签"""
    try:
        with open(KNOWLEDGE_TAGS_PATH, 'r', encoding='utf-8') as f:
            tags = json.load(f)
        return APIResponse(data=tags)
    except Exception as e:
        return APIResponse(code=500, message=f"读取失败: {str(e)}")

@router.get("/categories", response_model=APIResponse)
async def get_categories():
    """获取测评维度列表（对应6个分模块题库）"""
    categories = [
        {"name": "线性结构", "tag_count": 1, "module_id": "01"},
        {"name": "树与堆", "tag_count": 3, "module_id": "02"},
        {"name": "图与并查集", "tag_count": 3, "module_id": "03"},
        {"name": "排序算法", "tag_count": 2, "module_id": "04"},
        {"name": "哈希与缓存", "tag_count": 1, "module_id": "05"},
        {"name": "算法工具箱与综合", "tag_count": 1, "module_id": "06"},
    ]
    return APIResponse(data=categories)
