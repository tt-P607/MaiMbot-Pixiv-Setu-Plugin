import os
import base64
import time
import json
from typing import List, Tuple, Type
from pathlib import Path
from io import BytesIO
from PIL import Image
from src.common.logger import get_logger
from src.plugin_system import (
    BasePlugin, register_plugin, BaseAction,
    ComponentInfo, ActionActivationType, ChatMode
)
from src.plugin_system.base.config_types import ConfigField
import requests
import asyncio
from functools import partial

logger = get_logger("pixiv_setu_action")

@register_plugin
class PixivSetuPlugin(BasePlugin):
    """P站发图插件
    - 支持关键词或随机获取P站图片
    - Lolicon API 接入
    - 图片本地缓存与压缩
    - 完整的错误处理
    - 日志记录和监控
    """

    plugin_name = "pixiv_setu_plugin"
    plugin_description = "根据关键词或随机从Lolicon API获取P站图片"
    plugin_version = "1.0.0"
    plugin_author = "言柒"
    enable_plugin = True
    config_file_name = "config.toml"

    # 配置节描述
    config_section_descriptions = {
        "plugin": "插件基本配置",
        "components": "组件启用控制",
        "cache": "缓存相关配置",
        "logging": "日志记录配置",
    }

    # 配置Schema定义
    config_schema = {
        "plugin": {
            "config_version": ConfigField(type=str, default="1.0.0", description="插件配置文件版本号"),
            "enabled": ConfigField(type=bool, default=True, description="是否启用插件"),
        },
        "components": {
            "enable_pixiv_setu": ConfigField(type=bool, default=True, description="是否启用P站发图功能"),
        },
        "cache": {
            "expire_seconds": ConfigField(type=int, default=7200, description="缓存有效期(秒)"),
            "max_image_size": ConfigField(type=int, default=1048576, description="图片最大字节数(默认1MB)"),
        },
        "logging": {
            "level": ConfigField(
                type=str, default="INFO", description="日志级别", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
            ),
            "prefix": ConfigField(type=str, default="[PixivSetu]", description="日志前缀"),
        },
    }

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        components = []
        if self.get_config("components.enable_pixiv_setu", True):
            components.append((PixivSetuAction.get_action_info(), PixivSetuAction))
        return components

# =====================
    # 📋 manifest字段说明
    # =====================
    # plugin_name: 插件唯一英文标识，建议与文件夹名一致，禁止与其他插件重复。
    # plugin_description: 插件一句话简介，简明扼要描述插件功能。
    # plugin_version: 插件版本号，建议与config_version保持一致。
    # plugin_author: 插件作者信息。
    # enable_plugin: 是否启用插件，布尔值。
    # config_file_name: 插件配置文件名，通常为config.toml。
    # config_section_descriptions: 配置节说明，dict类型，描述每个配置节的用途。
    # config_schema: 配置schema定义，dict类型，详细描述每个配置项的类型、默认值、说明等。
    # get_plugin_components: 返回插件包含的所有组件（Action/Command等），用于插件系统自动注册。
    # =====================

class PixivSetuAction(BaseAction):
    """根据关键词或随机从Lolicon API获取P站图片"""

    focus_activation_type = ActionActivationType.KEYWORD
    normal_activation_type = ActionActivationType.KEYWORD
    mode_enable = ChatMode.ALL
    parallel_action = False

    action_name = "pixiv_setu"
    action_description = "根据关键词或随机从Lolicon API获取P站图片"
    activation_keywords = ["p站发图", "p站图片", "p站来一张", "p站", "pixiv"]
    keyword_case_sensitive = False

    action_parameters = {
        "keyword": "图片关键词，可选，不填则随机"
    }

    action_require = ["需要获取P站图片的场景","当有人要求你发P站图片时调用","当有人要求你或者@你发图片时调用"]
    associated_types = ["image"]

    CACHE_DIR = Path("cache/pixiv_setu")
    CACHE_FILE = CACHE_DIR / "setu.json"
    CACHE_EXPIRE = 2 * 60 * 60  # 2小时缓存

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # 兼容无global_config场景
        cfg = getattr(self, "global_config", None) or kwargs.get("global_config", {}) or {}
        cache_cfg = cfg.get("cache", {})
        self.max_image_size = cache_cfg.get("max_image_size", 1048576)

    async def get_setu_data(self, keyword=None):
        """获取图片数据，带缓存机制（仅缓存无关键词的单图）"""
        if not keyword and self.CACHE_FILE.exists():
            mtime = self.CACHE_FILE.stat().st_mtime
            if time.time() - mtime < self.CACHE_EXPIRE:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)

        api_url = "https://api.lolicon.app/setu/v2"
        params = {"num": 1}
        if keyword:
            params["tag"] = keyword

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            partial(
                requests.get,
                api_url,
                params=params,
                timeout=10,
            )
        )
        resp.raise_for_status()
        data = resp.json()

        if not keyword:
            with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        return data

    async def compress_image(self, img_bytes: bytes, max_size: int = None) -> bytes:
        """压缩图片到指定大小以内"""
        if max_size is None:
            max_size = self.max_image_size
        try:
            img = Image.open(BytesIO(img_bytes))
            img_format = img.format if img.format else "JPEG"
            quality = 90
            step = 5
            buffer = BytesIO()
            # 先尝试原尺寸压缩
            while True:
                buffer.seek(0)
                buffer.truncate()
                img.save(buffer, format=img_format, quality=quality)
                data = buffer.getvalue()
                if len(data) <= max_size or quality <= 30:
                    break
                quality -= step
            # 如果还超限，缩放分辨率
            while len(data) > max_size and (img.width > 300 or img.height > 300):
                new_width = int(img.width * 0.85)
                new_height = int(img.height * 0.85)
                img = img.resize((new_width, new_height), Image.LANCZOS)
                buffer.seek(0)
                buffer.truncate()
                img.save(buffer, format=img_format, quality=quality)
                data = buffer.getvalue()
            return data
        except Exception as e:
            logger.error(f"图片压缩失败: {e}")
            return img_bytes

    async def execute(self) -> Tuple[bool, str]:
        try:
            keyword = self.action_data.get("keyword")
            logger.info(f"请求P站图片，关键词: {keyword if keyword else '随机'}")

            setu_data = await self.get_setu_data(keyword)
            if not setu_data or "data" not in setu_data or not setu_data["data"]:
                return False, "没有获取到P站图片"

            item = setu_data["data"][0]
            image_url = item["urls"]["original"]
            title = item.get("title", "")
            author = item.get("author", "")
            pid = item.get("pid", "")

            loop = asyncio.get_event_loop()
            img_resp = await loop.run_in_executor(
                None,
                partial(
                    requests.get,
                    image_url,
                    timeout=10,
                    headers={"Referer": "https://www.pixiv.net/"}
                )
            )
            img_resp.raise_for_status()
            img_bytes = img_resp.content

            # 压缩图片
            img_bytes = await self.compress_image(img_bytes, self.max_image_size)
            base64_image = base64.b64encode(img_bytes).decode("utf-8")

            await self.send_text(f"已发送P站图片: {title} by {author} (pid: {pid})")
            await self.send_image(base64_image)
            return True, "发送了P站图片"
        except Exception as e:
            logger.error(f"获取P站图片失败: {e}")
            return False, "获取P站图片失败"