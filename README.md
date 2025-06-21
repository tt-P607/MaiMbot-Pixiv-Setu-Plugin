# pixiv_setu_plugin

根据关键词或随机从 Lolicon API 获取 P 站图片的插件。

## 功能简介
- 支持通过关键词或随机方式获取 Pixiv（P站）图片
- 可自定义插件启用、缓存、日志等配置
- 适用于娱乐、图片相关场景

## 配置说明
插件使用 `config.toml` 作为配置文件，主要配置项如下：

### [plugin] 插件基本配置
- `config_version`：配置文件版本号，默认 `1.0.0`
- `enabled`：是否启用插件，默认 `true`

### [components] 组件启用控制
- `enable_pixiv_setu`：是否启用 P 站发图功能，默认 `true`

### [cache] 缓存相关配置
- `expire_seconds`：缓存有效期（秒），默认 `7200`
- `max_image_size`：图片最大字节数，默认 `1048576`（1MB）

### [logging] 日志记录配置
- `level`：日志级别，支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`，默认 `INFO`
- `prefix`：日志前缀，默认 `[PixivSetu]`

## 使用方法
1. 配置好 `config.toml` 文件。
2. 启用插件后，根据指令或关键词获取图片。

## 许可证
MIT License

## 作者
言柒
