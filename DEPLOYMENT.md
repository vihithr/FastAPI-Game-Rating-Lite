# STG 社区网站部署文档

本文档说明如何在 Linux 服务器上部署 STG 社区网站。

## 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [手动部署步骤](#手动部署步骤)
- [配置说明](#配置说明)
- [服务管理](#服务管理)
- [故障排查](#故障排查)

## 系统要求

### 最低要求

- **操作系统**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+ / RHEL 8+
- **Python**: 3.8 或更高版本
- **内存**: 至少 **256MB RAM**（适合小型个人/测试环境）
- **磁盘空间**: 至少 **512MB 可用空间**（包含代码、虚拟环境和 SQLite 数据库）
- **网络**: 能够访问互联网（用于安装依赖和获取 SSL 证书）

> 实测：在单核 + 低内存机器上，应用常驻内存大约在 ~180MB 左右、磁盘占用在 ~200MB 量级，整体非常轻量。

### 推荐配置

- **CPU**: 1 核心或更多（单核即可满足一般访问量）
- **内存**: **512MB RAM 或更多**
- **磁盘**: SSD 推荐，至少 **1GB 可用空间**（便于后续文章、封面等内容增长）

## 快速开始

### 一键部署（推荐）

`vote_site` 是一个**完全独立的部署包**，包含所有必要的应用代码和配置文件。

1. **上传部署包到服务器**

   ```bash
   # 在本地打包（排除不必要的文件）
   tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
       --exclude='venv' --exclude='*.db' \
       -czf vote_site.tar.gz vote_site/
   
   # 上传到服务器
   scp vote_site.tar.gz user@your-server:/tmp/
   ```

2. **在服务器上解压并运行部署脚本**

   ```bash
   ssh user@your-server
   cd /tmp
   tar -xzf vote_site.tar.gz
   cd vote_site
   chmod +x deploy.sh
   sudo ./deploy.sh
   ```

   部署脚本会自动完成：
   - ✅ 检查系统依赖（Python、Caddy）
   - ✅ 创建专用用户 `stg_website`（非root，权限隔离）
   - ✅ 复制文件到 `/opt/stg_website`
   - ✅ 创建虚拟环境并安装依赖
   - ✅ 生成环境变量文件（包含自动生成的安全密钥）
   - ✅ 初始化数据库
   - ✅ 配置systemd服务
   - ✅ 配置Caddy反向代理
   - ✅ 启动所有服务

3. **（可选）配置环境变量**

   部署脚本会自动生成 `.env` 文件。如果需要修改：

   ```bash
   sudo nano /opt/stg_website/.env
   ```

4. **（可选）重启服务**

   ```bash
   sudo systemctl restart stg_website.service
   ```

## 手动部署步骤

如果自动部署脚本不适用于你的环境，可以按照以下步骤手动部署。

### 1. 安装系统依赖

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y python3 python3-pip python3-venv postfix caddy

# CentOS/RHEL
sudo yum install -y python3 python3-pip postfix
# Caddy 需要单独安装，参考 https://caddyserver.com/docs/install
```

### 2. 创建服务用户（权限隔离）

```bash
# 创建用户组
sudo groupadd -r stg_website

# 创建用户（不允许登录，主目录为安装目录）
sudo useradd -r -g stg_website -s /bin/false -d /opt/stg_website -c "STG Website Service User" stg_website
```

### 3. 创建项目目录

```bash
sudo mkdir -p /opt/stg_website
sudo chown stg_website:stg_website /opt/stg_website
```

### 4. 复制项目文件

```bash
# 复制整个vote_site目录内容到安装目录
sudo cp -r vote_site/* /opt/stg_website/

# 设置所有权
sudo chown -R stg_website:stg_website /opt/stg_website

# 设置文件权限（目录755，文件644）
sudo find /opt/stg_website -type d -exec chmod 755 {} \;
sudo find /opt/stg_website -type f -exec chmod 644 {} \;
```

### 5. 设置 Python 虚拟环境

```bash
cd /opt/stg_website

# 以服务用户身份创建虚拟环境
sudo -u stg_website python3 -m venv venv
sudo -u stg_website venv/bin/pip install --upgrade pip
sudo -u stg_website venv/bin/pip install -r requirements.txt

# 确保服务用户拥有venv目录
sudo chown -R stg_website:stg_website /opt/stg_website/venv
```

### 6. 配置环境变量

```bash
# 复制模板文件
sudo -u stg_website cp /opt/stg_website/env.example /opt/stg_website/.env

# 编辑环境变量（使用sudo以root权限编辑，然后设置正确的权限）
sudo nano /opt/stg_website/.env

# 设置安全权限（仅所有者可读）
sudo chmod 600 /opt/stg_website/.env
sudo chown stg_website:stg_website /opt/stg_website/.env
```

**重要**: 必须设置以下环境变量：

- `STG_SECRET_KEY`: JWT 签名密钥（生成命令：`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`）
- `STG_SESSION_SECRET_KEY`: 会话密钥（生成命令同上）
- `STG_SITE_BASE_URL`: 站点基础 URL（例如：`https://vote.stgcaomenlibrary.top/`）
- `STG_SENDER_ADDRESS`: 发件人邮箱地址

### 7. 初始化数据库

```bash
cd /opt/stg_website

# 加载环境变量
set -a
[ -f .env ] && source .env
set +a

# 以服务用户身份初始化数据库
sudo -u stg_website bash -c 'source venv/bin/activate && python3 -c "from app import models, database; models.Base.metadata.create_all(bind=database.engine)"'
sudo -u stg_website bash -c 'source venv/bin/activate && python3 -c "from app.main import init_bounty_categories; init_bounty_categories()"'

# 设置数据库文件权限
sudo chmod 600 /opt/stg_website/stg_website.db
sudo chown stg_website:stg_website /opt/stg_website/stg_website.db
```

### 7.5. 创建上传目录

```bash
# 创建上传目录
sudo mkdir -p /opt/stg_website/app/static/uploads/articles
sudo mkdir -p /opt/stg_website/app/static/uploads/covers

# 设置权限
sudo chown -R stg_website:stg_website /opt/stg_website/app/static/uploads
sudo chmod -R 755 /opt/stg_website/app/static/uploads
```

### 8. 配置 Systemd 服务

```bash
# 复制服务文件
sudo cp /opt/stg_website/stg_website.service /etc/systemd/system/

# 重新加载systemd
sudo systemctl daemon-reload

# 启用并启动服务
sudo systemctl enable stg_website.service
sudo systemctl start stg_website.service
```

**注意**: 服务文件已配置为使用 `stg_website` 用户运行，确保权限隔离。

### 9. 配置 Caddy 反向代理

```bash
# 编辑 Caddyfile，替换域名为你的实际域名
sudo cp Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile  # 修改域名

# 验证配置
sudo caddy validate --config /etc/caddy/Caddyfile

# 重启 Caddy
sudo systemctl restart caddy
```

### 10. 配置 DNS

确保你的域名 DNS 记录指向服务器 IP：

```
A 记录: vote.stgcaomenlibrary.top -> 服务器IP
```

## 配置说明

### 环境变量详解

所有环境变量都在 `env.example` 文件中有详细说明。主要配置项：

#### 安全配置

- `STG_SECRET_KEY`: JWT 签名密钥，必须使用强随机字符串
- `STG_SESSION_SECRET_KEY`: 会话密钥，必须使用强随机字符串
- `STG_HTTPS_ONLY`: 生产环境应设为 `true`

#### 站点配置

- `STG_SITE_BASE_URL`: 完整的站点 URL，用于生成邮件链接等
- `STG_MAX_TAGS_DISPLAY`: 浏览页面显示的最大标签数

#### 数据库配置

- `STG_DATABASE_URL`: 数据库连接字符串
  - SQLite（默认）: `sqlite:///./stg_website.db`
  - PostgreSQL: `postgresql://user:password@localhost/dbname`

#### 邮件配置

- `STG_SENDER_ADDRESS`: 发件人邮箱地址
- `STG_LOCAL_MAIL_HOST`: 本地邮件服务器地址（默认：localhost）
- `STG_LOCAL_MAIL_PORT`: 本地邮件服务器端口（默认：25）

### Gunicorn 配置

Gunicorn 配置文件位于 `gunicorn_config.py`，可以通过环境变量调整：

- `STG_GUNICORN_WORKERS`: Worker 进程数（默认：CPU核心数 × 2 + 1）
- `STG_LOG_LEVEL`: 日志级别（默认：info）

### Caddy 配置

Caddyfile 配置了：

- 自动 HTTPS（Let's Encrypt）
- 反向代理到 Gunicorn（127.0.0.1:8000）
- Gzip 压缩
- 安全响应头

## 服务管理

### 查看服务状态

```bash
# 应用服务
sudo systemctl status stg_website.service

# Caddy 服务
sudo systemctl status caddy
```

### 查看日志

```bash
# 应用日志（实时）
sudo journalctl -u stg_website.service -f

# 应用日志（最近 100 行）
sudo journalctl -u stg_website.service -n 100

# Caddy 日志
sudo journalctl -u caddy -f

# Nginx 错误日志（如果使用 Nginx 而不是 Caddy）
sudo tail -f /var/log/nginx/error.log
```

### 重启服务

```bash
# 重启应用
sudo systemctl restart stg_website.service

# 重启 Caddy
sudo systemctl restart caddy

# 重新加载 Caddy 配置（不中断服务）
sudo systemctl reload caddy
```

### 停止/启动服务

```bash
sudo systemctl stop stg_website.service
sudo systemctl start stg_website.service
```

## 故障排查

### 服务无法启动

1. **检查服务状态**

   ```bash
   sudo systemctl status stg_website.service
   ```

2. **查看详细错误日志**

   ```bash
   sudo journalctl -u stg_website.service -n 50 --no-pager
   ```

3. **检查环境变量**

   ```bash
   sudo -u www-data cat /opt/stg_website/.env
   ```

4. **检查文件权限**

   ```bash
   ls -la /opt/stg_website/
   # 确保 www-data 用户有读写权限
   ```

### 502 Bad Gateway

这通常表示 Caddy 无法连接到 Gunicorn。

1. **检查 Gunicorn 是否运行**

   ```bash
   sudo systemctl status stg_website.service
   ```

2. **检查端口是否监听**

   ```bash
   sudo netstat -tlnp | grep 8000
   # 或
   sudo ss -tlnp | grep 8000
   ```

3. **检查防火墙**

   ```bash
   # 确保本地回环接口可以访问
   curl http://127.0.0.1:8000
   ```

### SSL 证书问题

如果 Caddy 无法自动获取 SSL 证书：

1. **检查 DNS 配置**

   确保域名正确解析到服务器 IP

2. **检查防火墙**

   确保 80 和 443 端口开放

3. **查看 Caddy 日志**

   ```bash
   sudo journalctl -u caddy -n 50
   ```

4. **手动测试证书申请**

   ```bash
   sudo caddy validate --config /etc/caddy/Caddyfile
   ```

### 数据库问题

1. **检查数据库文件权限**

   ```bash
   ls -la /opt/stg_website/stg_website.db
   ```

2. **检查数据库连接**

   ```bash
   cd /opt/stg_website
   sudo -u www-data venv/bin/python3 -c "from app import database; print(database.SQLALCHEMY_DATABASE_URL)"
   ```

### 邮件发送问题

1. **检查 Postfix 状态**

   ```bash
   sudo systemctl status postfix
   ```

2. **测试本地邮件发送**

   ```bash
   echo "Test email" | mail -s "Test" your-email@example.com
   ```

3. **检查邮件日志**

   ```bash
   sudo tail -f /var/log/mail.log
   ```

### 性能优化

1. **调整 Gunicorn Workers**

   编辑 `/opt/stg_website/gunicorn_config.py` 或设置环境变量 `STG_GUNICORN_WORKERS`

2. **启用数据库连接池**

   如果使用 PostgreSQL，可以在 `STG_DATABASE_URL` 中添加连接池参数

3. **静态文件缓存**

   Caddy 可以配置静态文件缓存，减少应用服务器负载

## 备份与恢复

### 备份数据库

```bash
# SQLite
sudo cp /opt/stg_website/stg_website.db /backup/stg_website_$(date +%Y%m%d).db

# PostgreSQL（如果使用）
pg_dump -U user dbname > /backup/stg_website_$(date +%Y%m%d).sql
```

### 备份上传文件

```bash
sudo tar -czf /backup/uploads_$(date +%Y%m%d).tar.gz /opt/stg_website/app/static/uploads/
```

### 恢复

```bash
# 停止服务
sudo systemctl stop stg_website.service

# 恢复数据库
sudo cp /backup/stg_website_YYYYMMDD.db /opt/stg_website/stg_website.db
sudo chown www-data:www-data /opt/stg_website/stg_website.db

# 恢复上传文件
sudo tar -xzf /backup/uploads_YYYYMMDD.tar.gz -C /

# 启动服务
sudo systemctl start stg_website.service
```

## 更新部署

1. **备份当前版本**

   ```bash
   sudo systemctl stop stg_website.service
   sudo cp -r /opt/stg_website /opt/stg_website.backup
   ```

2. **更新代码**

   ```bash
   cd /opt/stg_website
   sudo -u www-data git pull  # 如果使用 Git
   # 或手动复制新文件
   ```

3. **更新依赖**

   ```bash
   cd /opt/stg_website
   sudo -u www-data venv/bin/pip install -r requirements.txt --upgrade
   ```

4. **运行数据库迁移（如果有）**

   ```bash
   cd /opt/stg_website
   sudo -u www-data venv/bin/alembic upgrade head
   ```

5. **重启服务**

   ```bash
   sudo systemctl restart stg_website.service
   ```

## 安全建议

1. **定期更新系统包**

   ```bash
   sudo apt update && sudo apt upgrade
   ```

2. **使用防火墙**

   只开放必要的端口（80, 443, 22）

3. **定期备份**

   设置自动备份脚本

4. **监控日志**

   定期检查日志文件，发现异常活动

5. **使用强密码**

   确保所有密钥和密码都是强随机字符串

6. **限制文件权限**

   确保 `.env` 文件权限为 600，只有所有者可读

## 支持与帮助

如果遇到问题：

1. 查看日志文件
2. 检查本文档的故障排查部分
3. 查看项目文档：`PROJECT_OVERVIEW.md`

---

**最后更新**: 2025-01-18

