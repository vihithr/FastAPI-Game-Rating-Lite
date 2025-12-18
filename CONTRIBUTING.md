## 贡献指南 / Contributing

欢迎对 **FastAPI-Game-Rating-Lite** 提出问题、建议和代码贡献！下面是一个简要的贡献流程说明。

---

## 问题反馈（Issues）

- **先搜索**：在创建 Issue 前，请先搜索现有 Issue，避免重复。  
- **提供关键信息**：
  - 系统发行版（如 Ubuntu 22.04）
  - Python 版本
  - 使用的部署方式（GitHub 一键脚本 / 压缩包 / 本地开发）
  - 相关日志片段（如 `journalctl -u stg_website.service -n 50`）  

---

## 本地开发环境

1. 克隆仓库：

```bash
git clone https://github.com/<owner>/FastAPI-Game-Rating-Lite.git
cd FastAPI-Game-Rating-Lite/vote_site
```

2. 创建虚拟环境并安装依赖：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

3. 准备开发环境配置（可直接使用 SQLite 开发库）：

```bash
cp env.example .env  # 如有需要，可手动修改
```

或显式设置环境变量：

```bash
export STG_DATABASE_URL="sqlite:///./stg_website_dev.db"
export STG_SECRET_KEY="dev-secret"
export STG_SESSION_SECRET_KEY="dev-session-secret"
```

4. 初始化数据库（仅第一次需要）：

```bash
python -c "from app import models, database; models.Base.metadata.create_all(bind=database.engine)"
```

5. 启动开发服务（示例，具体入口以代码为准）：

```bash
uvicorn app.main:app --reload
```

访问本地地址（例如 `http://127.0.0.1:8000`）即可查看站点。

---

## 代码规范

- **Python**：尽量遵循 PEP 8，保持现有代码风格一致。  
- **提交信息**：使用简洁明了的英文或中英文混合描述改动内容。  
- **小步提交**：功能改动尽量拆分为多个小的、可回滚的提交。  

如果你引入了新的依赖，请记得更新 `requirements.txt` 并在 PR 描述中说明原因。

---

## 提交 Pull Request

1. 从 `main`（或指定开发分支）创建功能分支：

```bash
git checkout -b feature/my-awesome-change
```

2. 完成修改并自测（至少确认脚本、服务可正常启动）。  
3. 提交前请确保没有敏感信息（如测试用 `.env`、数据库文件）被加入版本控制。  
4. 提交 PR 时请说明：
   - 改动动机（解决了什么问题 / 增加了什么功能）  
   - 大致实现思路  
   - 是否有向下兼容性影响（例如数据库结构更改）  

感谢你的贡献！  


