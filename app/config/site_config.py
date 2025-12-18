"""
站点配置加载模块
从JSON配置文件加载站点相关配置，提供统一的配置访问接口
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from .constants import BASE_DIR

logger = logging.getLogger(__name__)

# 默认配置（作为fallback）
DEFAULT_CONFIG = {
    "site": {
        "name": "STG社区评价",
        "brand": "STG Ratings",
        "title": "STG社区评价",
        "subtitle": "一个由社区驱动的STG游戏评价平台",
        "app_title": "STG Community Ratings"
    },
    "ratings": {
        "quality": {
            "dimensions": [
                {"name": "趣味性", "field": "fun"},
                {"name": "核心设计", "field": "core"},
                {"name": "深度", "field": "depth"},
                {"name": "演出", "field": "performance"},
                {"name": "剧情", "field": "story"}
            ]
        },
        "difficulty": {
            "dimensions": [
                {"name": "避弹", "field": "dodge"},
                {"name": "策略", "field": "strategy"},
                {"name": "执行", "field": "execution"}
            ]
        }
    },
    "difficulty_realm": {
        "max_score": 60,
        "realms": [
            {"threshold": 0, "name": "N/A"},
            {"threshold": 5, "name": "见习一"},
            {"threshold": 10, "name": "见习二"},
            {"threshold": 15, "name": "新手一"},
            {"threshold": 20, "name": "新手二"},
            {"threshold": 25, "name": "入门一"},
            {"threshold": 30, "name": "入门二"},
            {"threshold": 35, "name": "进阶一"},
            {"threshold": 40, "name": "进阶二"},
            {"threshold": 45, "name": "上级一"},
            {"threshold": 50, "name": "上级二"},
            {"threshold": 55, "name": "上级三"},
            {"threshold": None, "name": "论外"}
        ]
    },
    "stats": {
        "difficulty_stats": {
            "columns": {
                "game": "游戏",
                "difficulty_level": "难度等级",
                "ship_type": "机体/角色",
                "dodge": "避弹",
                "strategy": "策略",
                "execution": "执行",
                "overall_avg": "平均分",
                "realm": "段位",
                "rating_count": "评分数"
            }
        }
    },
    "email": {
        "password_reset": {
            "subject_template": "{site_name} - 密码重置通知",
            "title_template": "{site_name} 密码重置"
        }
    }
}

# 全局配置缓存
_config_cache: Optional[Dict[str, Any]] = None


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    加载配置文件
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        配置字典，如果加载失败则返回默认配置
    """
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    if config_path is None:
        config_path = BASE_DIR / "app" / "config" / "site_config.json"
    
    try:
        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            _config_cache = DEFAULT_CONFIG.copy()
            return _config_cache
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 合并默认配置，确保所有必需字段都存在
        merged_config = _deep_merge(DEFAULT_CONFIG.copy(), config)
        _config_cache = merged_config
        logger.info(f"成功加载配置文件: {config_path}")
        return _config_cache
        
    except json.JSONDecodeError as e:
        logger.error(f"配置文件JSON格式错误: {e}，使用默认配置")
        _config_cache = DEFAULT_CONFIG.copy()
        return _config_cache
    except Exception as e:
        logger.error(f"加载配置文件时出错: {e}，使用默认配置")
        _config_cache = DEFAULT_CONFIG.copy()
        return _config_cache


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """深度合并两个字典"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_config() -> Dict[str, Any]:
    """获取配置（懒加载）"""
    if _config_cache is None:
        load_config()
    return _config_cache or DEFAULT_CONFIG


def reload_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """重新加载配置"""
    global _config_cache
    _config_cache = None
    return load_config(config_path)


# 便捷访问函数
def get_site_config() -> Dict[str, Any]:
    """获取站点配置"""
    return get_config().get("site", {})


def get_quality_dimensions() -> List[Dict[str, str]]:
    """获取品质评分维度"""
    return get_config().get("ratings", {}).get("quality", {}).get("dimensions", [])


def get_difficulty_dimensions() -> List[Dict[str, str]]:
    """获取难度评分维度"""
    return get_config().get("ratings", {}).get("difficulty", {}).get("dimensions", [])


def get_difficulty_realms() -> List[Dict[str, Any]]:
    """获取难度段位配置"""
    return get_config().get("difficulty_realm", {}).get("realms", [])


def get_difficulty_max_score() -> int:
    """获取难度评分最大值"""
    return get_config().get("difficulty_realm", {}).get("max_score", 60)


def get_stats_columns() -> Dict[str, str]:
    """获取统计页面列名配置"""
    return get_config().get("stats", {}).get("difficulty_stats", {}).get("columns", {})


def get_email_config() -> Dict[str, Any]:
    """获取邮件配置"""
    return get_config().get("email", {})


# 初始化时加载配置
load_config()

