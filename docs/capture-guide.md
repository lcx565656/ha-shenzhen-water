# 深圳水务抓包说明

本文用于确认 Home Assistant 集成需要填写哪些字段，以及如何在 Charles 里找到它们。

## 需要填写

当前配置表单需要 1 个必填字段：

* OpenId

水务户号、`Utoken`、`GUID` 不需要填写。集成会尝试用 `OpenId` 调用小程序 `AutomaticLoginV20` 自动刷新 `Utoken` 和 `GUID`，再通过 `GetUsersV20` 自动读取已绑定户号。

本次抓包确认：`OpenId` 在登录后的深圳水务请求头和请求体里可以抓到；`GUID` 由 `AutomaticLoginV20` 返回，不再作为配置项。

## 抓包步骤

1. 打开 Charles，并确保手机或电脑微信流量已经走 Charles 代理。
2. 打开微信小程序“环水管家”。
3. 进入户号或账单页面，触发一次账单查询。
4. 在 Charles 左侧找到域名：

```text
szgk.sz-water.com.cn
```

5. 优先查看下面几个登录后的请求：

```text
/api/wechat/op/user/GetUsersV20
/api/wechat/op/BillInfo/GetLatestBillDetails2V30
/api/wechat/op/user/billInfo/BillingInfoBycustomerCodesV30
```

6. 点开请求后，优先复制：

```text
OpenId
```

注意：登录前的请求里 `OpenId` 和 `Utoken` 可能是空的。要看 `AutomaticLoginV20` 之后的请求，也就是 `GetUsersV20` 或账单接口。

## 户号在哪里

户号不需要手动填写。集成会从 `GetUsersV20` 响应里的用户列表拿 `customerCode`。

如果需要人工核对，也可以从小程序页面直接看，或在 Charles 里找类似请求：

```text
/api/wechat/op/Customer/checkFaceInfoNew/wxxcx/{户号}/{手机号}
```

其中 `{户号}` 就是水务户号。

## 已确认的接口

本次 HAR 确认小程序账单相关接口路径是：

```text
/api/wechat/op/BillInfo/GetLatestBillDetails2V30
/api/wechat/op/BillInfo/GetLatestBillDetailsV30
/api/wechat/op/user/billInfo/BillingInfoBycustomerCodesV30
/api/wechat/op/user/CustomerInfo/GetCustomerDetailV20
```

当前集成使用：

```text
/api/wechat/op/BillInfo/GetLatestBillDetails2V30
/api/wechat/op/user/billInfo/BillingInfoBycustomerCodesV30
```

这两个路径和抓包一致。

## 已确认的加密方式

小程序 `wxxcx` 渠道的 POST 请求体和响应都是加密字符串，与旧网厅 `wt` 渠道的 AES 密钥常量不同。

本次从 `wx987545bf02573f61` 小程序包确认：

* 请求头 `04A52C9F` 是 32 位大写字母/数字
* AES key 为 `CD3AA097 + 04A52C9F[8:24] + CE92AD77`
* AES 模式为 ECB，填充为 PKCS7
* 响应密文需要做段位交换：`body[:7] + body[20:] + body[7:20]`

如果 Home Assistant 里添加集成时报「OpenId 无效」，优先检查 `OpenId` 是否取自登录后的请求（登录前的请求里它可能是空的）。

## 关于 Utoken 过期

集成会自动处理：业务接口返回 401 或空响应时，会重新调用 `AutomaticLoginV20` 换新 Utoken 再重试一次。如果重试仍失败，实体会显示为不可用（而不是空值），错误详情在 HA 日志里搜索 `shenzhen_water`。
