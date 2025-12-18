## FastAPI-Game-Rating-Lite（STG 社区站独立部署版）

**FastAPI-Game-Rating-Lite** 是一个基于 FastAPI 的轻量级游戏评分 / 社区站点模板，当前主要面向 STG（纵版/弹幕射击）玩家。本目录是该站点的 **独立部署版本**，包含运行线上实例所需的全部代码和运维脚本，适合作为一个完整的 GitHub 开源项目使用。

本项目底层部署技术由 [FastAPI-Caddy-Systemd-OneKey](https://github.com/vihithr/FastAPI-Caddy-Systemd-OneKey) 提供支持。

- **后端框架**: Python 3 / FastAPI + SQLAlchemy（SQLite 默认）  
- **前端**: 服务器端模板渲染（Jinja2），配合少量原生 JS/CSS  
- **部署方式**: 一键脚本部署到 Linux 服务器（Systemd + Gunicorn + Caddy）  

> English readers: **FastAPI-Game-Rating-Lite** is a lightweight game rating/community site template (currently tailored for STG / shoot 'em up games), powered by FastAPI + SQLite and shipped with a one‑command deployment script (`deploy.sh`). See the “Quick Start” section below for commands.

---

## 功能特点

- ✅ **完全独立部署包**：包含所有应用代码和配置文件，不依赖外部目录  
- ✅ **一键安装 / 更新**：通过 `deploy.sh` 完成安装、更新、服务管理和反向代理配置  
- ✅ **权限隔离**：自动创建专用非 root 用户 `stg_website` 运行服务  
- ✅ **集中管理**：所有安装内容集中在 `/opt/stg_website` 目录下  
- ✅ **安全默认值**：自动生成 JWT / Session 密钥，强制使用 SQLite 本地数据库  

---

## 目录结构概览

- `app/`：应用代码（FastAPI、模型、路由、模板、静态资源等）  
- `alembic/`：数据库迁移脚本  
- `deploy.sh`：一键部署 / 更新 / 卸载脚本  
- `env.example`：环境变量模板  
- `requirements.txt`：Python 依赖列表  
- `stg_website.service`：Systemd 服务单元模板  
- `Caddyfile`：Caddy 反向代理模板（HTTPS / HTTP 配置）  
- `gunicorn_config.py`：Gunicorn 配置  
- [`DEPLOYMENT.md`](DEPLOYMENT.md)：更详细的部署说明与故障排查  

---

## 快速开始（生产部署）

### 1. 服务器要求

- Linux（Ubuntu 20.04+ / Debian 11+ / CentOS 8+）  
- Python 3.8+  
- 拥有 root 或 sudo 权限  
- 推荐配置（实测运行非常轻量）：  
  - CPU：1 vCPU 即可  
  - 内存：**≥ 256MB（推荐 512MB）**  
  - 磁盘：**≥ 512MB 可用空间（推荐 1GB 以上）**  

### 2. 在线一键部署（推荐，从本仓库拉取）

完整的部署说明和所有模式（从 GitHub 克隆、Release 源码包、离线本地包等）已迁移到 [`DEPLOYMENT.md`](DEPLOYMENT.md)。  
这里只保留一个**最推荐、可直接复制的生产环境 Quick Start**。

**场景：新服务器，直接以 `root` 登录，有域名，使用 Release `v0.1.0` 源码包 + HTTPS，一行命令完成下载与安装：**

```bash
bash -c 'cd /tmp && \
  curl -L -o stg_website_v0.1.0.tar.gz https://github.com/vihithr/FastAPI-Game-Rating-Lite/archive/refs/tags/v0.1.0.tar.gz && \
  bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
    install --from-archive /tmp/stg_website_v0.1.0.tar.gz --domain example.com'
```

- 将命令中的 `example.com` 替换为你的实际域名。  
- 如果你是普通用户而非 root，请改用：

  ```bash
  sudo bash -c 'cd /tmp && \
    curl -L -o stg_website_v0.1.0.tar.gz https://github.com/vihithr/FastAPI-Game-Rating-Lite/archive/refs/tags/v0.1.0.tar.gz && \
    bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
      install --from-archive /tmp/stg_website_v0.1.0.tar.gz --domain example.com'
  ```

- 若没有域名、只想用 IP 访问，可把末尾的 `--domain example.com` 改成 `--ip`。  
- 更多部署模式与参数说明请查看 [`DEPLOYMENT.md`](DEPLOYMENT.md) 中的“快速开始”与“手动部署步骤”章节。  

### 3. 离线 / 本地部署（可选）

如果你的服务器无法直接访问 GitHub，或者需要通过压缩包离线部署，请参考 `DEPLOYMENT.md` 中的“离线 / 本地部署”章节。  

部署脚本在安装时会自动完成：

- 检查系统依赖（Python、邮件服务等）  
- 创建专用用户 `stg_website`（非 root，权限隔离）  
- 同步代码至 `/opt/stg_website`  
- 在 `/opt/stg_website/venv` 中创建虚拟环境并安装依赖  
- 生成 `.env` 并自动填充密钥 / 数据库配置  
- 初始化 SQLite 数据库  
- 配置 Systemd 服务 & Caddy 反向代理  
- 启动应用服务和 Caddy  

**安装完成后，相关路径汇总**：

- 应用代码：`/opt/stg_website/app/`  
- 虚拟环境：`/opt/stg_website/venv/`  
- 数据库：`/opt/stg_website/stg_website.db`  
- 环境变量：`/opt/stg_website/.env`  
- Caddy 二进制：`/opt/stg_website/caddy/`  

---

## 环境变量与配置

部署脚本会自动生成 `.env`，如需手动调整：

```bash
sudo nano /opt/stg_website/.env
```

关键配置项：

- `STG_SECRET_KEY`：JWT 签名密钥（自动生成）  
- `STG_SESSION_SECRET_KEY`：会话密钥（自动生成）  
- `STG_SITE_BASE_URL`：站点完整 URL（根据域名 / IP 自动写入，可手动修改）  
- `STG_SENDER_ADDRESS`：发件人邮箱（用于密码重置等功能）  

修改 `.env` 后可通过下方命令重启服务：

```bash
sudo systemctl restart stg_website.service
```

---

## 反向代理：Caddy

本项目推荐使用 Caddy 作为前端反向代理，优势包括：

- 自动 HTTPS（Let's Encrypt）  
- 简洁的配置语法  
- HTTP/2 / HTTP/3 支持  
- 热重载 / 零停机配置更新  

部署脚本会自动安装 Caddy 并应用合适配置：  
- 域名模式下使用 `Caddyfile` 模板，并将示例域名替换成你传入的 `--domain`  
- IP 模式下自动生成仅 HTTP 的 Caddy 配置  

如需手动微调，请参考 `DEPLOYMENT.md`。  

---

## 服务管理

```bash
# 查看服务状态
sudo systemctl status stg_website.service

# 实时查看日志
sudo journalctl -u stg_website.service -f

# 重启服务
sudo systemctl restart stg_website.service

# 停止服务
sudo systemctl stop stg_website.service
```

---

## 卸载

完全卸载（包含数据目录，执行前请备份数据库）：

```bash
cd /opt/stg_website || cd /path/to/vote_site
sudo ./deploy.sh uninstall
```

卸载脚本会：

- 停止并禁用 Systemd 服务  
- 删除服务单元文件  
- 询问是否删除配置文件和安装目录（包含 SQLite 数据库）  
- 询问是否删除服务用户与用户组  

---

## 本地开发（简要说明）

如果你想在本地修改代码 / 调试，可以按如下方式启动开发环境（示例）：

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export STG_DATABASE_URL="sqlite:///./stg_website_dev.db"
export STG_SECRET_KEY="dev-secret"
export STG_SESSION_SECRET_KEY="dev-session-secret"

uvicorn app.main:app --reload
```

> 具体模型结构、API 说明、Alembic 迁移命令等，请参考代码中的注释或后续在 `CONTRIBUTING.md` 中补充的开发文档。

---

## 安全与注意事项

1. 生产环境务必使用**强随机密钥**（脚本已自动生成一份，但建议妥善备份）。  
2. `.env` 文件权限应为 `600`，仅服务用户可读。  
3. 确保你的域名解析正确指向服务器 IP，并开放 80 / 443 端口。  
4. 数据库文件默认位于本地磁盘，注意定期备份。  

---

## 故障排查

若遇到问题，可以从以下几步排查：

1. 查看应用日志：`sudo journalctl -u stg_website.service -n 50`  
2. 查看 Caddy 日志：`sudo journalctl -u caddy -n 50`  
3. 参考 `DEPLOYMENT.md` 中更详细的故障排查章节  
4. 提交 Issue 时，建议附上：系统发行版、Python 版本、部署命令、相关日志片段  

