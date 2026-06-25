# Novel Reader

多源小说阅读器，支持桌面端和移动端。

## 功能

- 多小说源支持
- 桌面端分页阅读 + 移动端滚动阅读
- 夜间/日间模式（移动端）
- 阅读历史同步
- CAPTCHA 验证码识别支持
- SOCKS5 代理自动切换（反爬虫）

## 技术栈

- Python / Flask
- SQLite
- BeautifulSoup + lxml
- Xray-core（代理节点管理）
- Font Awesome

## 快速开始

```bash
# 安装依赖
pip install flask flask-limiter pycryptodome requests beautifulsoup4 lxml bcrypt

# 初始化数据库并启动服务
python app.py
```

服务默认运行在 `http://localhost:5000`。

也可使用 `run.sh` 一键管理：

```bash
bash run.sh start     # 启动（含 venv + xray + flask）
bash run.sh stop      # 停止
bash run.sh restart   # 重启
bash run.sh status    # 查看状态
```

## 配置

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `PROXY_SUB_URL` | VLess 代理订阅地址（可选，用于反爬虫） | `""` |

## 注意事项

- 默认管理员账号/密码存储在 `data/admin_credentials.txt`
- 代理订阅需通过环境变量 `PROXY_SUB_URL` 设置，不提交到仓库
- 移动端 PIN 锁密码：`2356`
