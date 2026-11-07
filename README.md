# 深圳水务 HA 集成

用于 Home Assistant 的深圳水务自定义集成，按 `ha-shenzhen-gas` 的模式重做：通过微信小程序接口读取水务账单，不再使用短信登录、网厅登录或短期 Ctoken 流程。

## 功能

* 支持 Home Assistant UI 添加集成
* 使用“环水管家”微信小程序抓包得到的 OpenId
* 支持用 OpenId 调用小程序自动登录接口刷新 Utoken/GUID
* 自动读取已绑定水务户号，多个户号时提供选择
* 使用小程序账单接口获取本期账单、用水量、水表读数、缴费状态等信息
* 默认每 6 小时同步一次，避免高频请求
* 保留原深圳水务实体

## 实体

当前会创建以下传感器：

* 账单月份
* 缴费状态
* 到期日
* 本期用水量
* 当前水表读数
* 本期总费用
* 应缴金额
* 自来水费
* 污水处理费
* 垃圾费
* 上期账单月份
* 上期用水量
* 上期总费用

## 安装

通过 HACS 自定义仓库安装：

```text
https://github.com/Chaxcy/ha-shenzhen-water
```

类型选择：

```text
Integration
```

安装后重启 Home Assistant。

## 配置

1. 打开 Home Assistant
2. 进入“设置” -> “设备与服务”
3. 点击“添加集成”
4. 搜索“深圳水务”
5. 输入从“环水管家”微信小程序抓到的 OpenId
6. 如果这个 OpenId 绑定了多个户号，选择要添加的户号

添加时会请求一次小程序账单接口校验信息是否可用。

### OpenId 失效了怎么办

进入「设置 → 设备与服务 → 深圳水务 → 配置」，直接改 OpenId 再保存即可，不需要删掉集成重加。保存时会立即校验，校验通过后自动重载。

### 设置项

在同一个「配置」页面还能改**刷新间隔**，默认 360 分钟（6 小时），可填 30 ~ 1440。水务账单更新很慢，不建议调得太频繁。

其余参数（API 域名、小程序 appid / 版本、TenantId、Channel、User-Agent、AES 密钥常量、请求超时）对所有人都一样，已经内置在 [`const.py`](custom_components/shenzhen_water/const.py) 里，不需要任何配置文件。

### 敏感信息保存在哪

OpenId、户号**只保存在你自己 Home Assistant 的 `config/.storage/core.config_entries` 里**，由你在网页表单中填写。仓库里不含任何个人数据。

## 抓包提示

用 Charles 打开微信小程序“环水管家”，进入账单或户号页面，关注 `szgk.sz-water.com.cn` 下的请求。通常可在登录后的账单请求头里找到：

* `OpenId`

`customercode`、`Utoken`、`GUID` 不需要填写，集成会自动读取或刷新。

详细步骤见 [抓包说明](docs/capture-guide.md)。

## 免责声明

本项目为非官方 Home Assistant 自定义集成，仅用于个人学习和家庭自动化使用。

本项目与深圳水务官方无任何关联。接口可能因官方调整而失效，请勿高频请求。

## License

MIT
