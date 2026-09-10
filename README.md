# 硅基动感亲友分享 → Nightscout 上传器

通过硅基 SIJOY 微信小程序的亲友分享 API，定时拉取血糖数据并上传到 Nightscout。支持 Docker 部署，可独立 7×24 运行，不依赖手机或电脑。

## 功能

- 从硅基云端 API 拉取亲友分享的实时血糖数据
- 自动转换为 Nightscout 格式（含血糖趋势方向计算）
- 每 5 分钟自动同步（可配置）
- 支持 Docker / Railway / 本地运行

## 数据流向

```
GS3 传感器 → 手表/手机 → 硅基云端 → 本脚本 → Nightscout
```

## 快速部署（Railway 推荐，免费）

1. Fork 本仓库
2. 登录 [Railway](https://railway.app)，New Project → GitHub Repository → 选择本仓库
3. 在 Variables 页面添加以下环境变量：

| 变量名 | 说明 | 示例 |
|---|---|---|
| `SI_FOLLOW_RELATION_ID` | 亲友关系 ID（抓包获取） | `2088455721451631438` |
| `SI_DEVICE_ID` | 设备 ID（抓包获取） | `2095153918479945148` |
| `SI_AUTH_TOKEN` | 硅基认证 Token（抓包获取，不含 Bearer） | `c3217d8f-e448-...` |
| `NS_URL` | Nightscout 网址 | `https://xxx.abwsz.com` |
| `NS_API_SECRET` | Nightscout API-SECRET（密码的 SHA1） | `1160a3a8...` |
| `POLL_INTERVAL` | 轮询间隔（秒），默认 300 | `300` |

4. 点击 Deploy，等待构建完成即可

## Docker 部署

```bash
docker build -t sisensing-nightscout-uploader .
docker run -d \
  --name sisensing-uploader \
  --restart unless-stopped \
  -e SI_FOLLOW_RELATION_ID=你的亲友关系ID \
  -e SI_DEVICE_ID=你的设备ID \
  -e SI_AUTH_TOKEN=你的Token \
  -e NS_URL=https://你的nightscout地址 \
  -e NS_API_SECRET=你的API_SECRET_SHA1 \
  sisensing-nightscout-uploader
```

## 本地运行

```bash
pip install -r requirements.txt
# 单次运行
python sisensing_nightscout_uploader.py
# 持续运行
python sisensing_nightscout_uploader.py --daemon
```

## 如何获取硅基 API 参数（抓包）

1. 电脑安装 Fiddler，开启 HTTPS 解密
2. 电脑版微信打开硅基 SIJOY 小程序，进入血糖页面
3. 在 Fiddler 中找到 `cxm-api.sisensing.com` 的请求
4. 从 URL 参数中获取 `followRelationId` 和 `deviceId`
5. 从请求头 `Authorization` 中获取 Token（Bearer 后面的部分）

## Nightscout API-SECRET 计算

```bash
echo -n "你的Nightscout登录密码" | sha1sum
```

## 注意事项

- 硅基 Token 可能会过期，若出现 401 错误需重新抓包更新
- 数据延迟约 5 分钟（硅基本身每 5 分钟产生一个数据点）
- 本脚本仅用于血糖数据同步，不具备远程给药功能
