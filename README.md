# Novel Reader

多源小说阅读器，支持桌面端和移动端。

## 功能

- 多小说源（爱丽丝书屋、笔趣阁）
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

## 项目结构

```
novel-reader/
├── app.py                  # Flask 入口
├── database.py             # SQLite 数据库操作
├── run.sh                  # 启动脚本
├── spiders/
│   ├── base.py             # 爬虫基类
│   ├── alicesw.py          # 爱丽丝书屋爬虫
│   ├── biquge.py           # 笔趣阁爬虫
│   └── proxy_manager.py    # 代理订阅管理
├── templates/
│   ├── index.html          # 桌面端
│   ├── mobile.html         # 移动端
│   └── login.html          # 登录页
├── static/                 # 静态资源
└── data/                   # 运行时数据
```

## API

| 路径 | 方法 | 说明 |
|---|---|---|
| `/api/login` | POST | 登录 |
| `/api/sites` | GET | 获取小说源列表 |
| `/api/history` | GET | 获取阅读历史 |
| `/api/history/save` | POST | 保存阅读进度 |
| `/api/alicesw/novel/load` | POST | 加载小说信息+章节列表 |
| `/api/alicesw/chapter/load` | POST | 加载章节内容 |
| `/api/alicesw/session/reset` | POST | 重置爬虫会话 |

## 注意事项

- 默认管理员账号/密码存储在 `data/admin_credentials.txt`
- 代理订阅需通过环境变量 `PROXY_SUB_URL` 设置，不提交到仓库
- 移动端 PIN 锁密码：`2356`
