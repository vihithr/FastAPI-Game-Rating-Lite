## FastAPI-Game-Rating-Lite（STG 社区站独立部署版）

**FastAPI-Game-Rating-Lite** 是一个基于 FastAPI 的轻量级游戏评分 / 社区站点模板，当前主要面向 STG（纵版/弹幕射击）玩家。本目录是该站点的 **独立部署版本**，包含运行线上实例所需的全部代码和运维脚本，适合作为一个完整的 GitHub 开源项目使用。

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

### 站点功能

| 模块 | 说明 |
|---|---|
| 作品库 | 品质评分（5 维度）+ 难度评分（3 维度）双轨评价，支持标签、公司、**平台**筛选与三种浏览视图 |
| 难度统计 | 难度分布、维度雷达、玩家分段对比 |
| **资料库** | 独立于评分库的只读作品档案（封面/年份/平台/系列/简介/外部链接），支持关键词、平台、年代、标签检索 |
| 文章 / 专栏 | ToastUI 编辑器，支持图文混合与静态资料包 |
| 资源索引 | 分类、标签、热度、有效/失效投票 |
| 悬赏板 | 分类、状态流转、评论区 |
| 主题 | 深色 / 浅色双主题，`localStorage` 记忆，首帧无闪烁 |

### 数据工具（`tools/`）

| 脚本 | 用途 |
|---|---|
| `import_library.py` | 把采集来的作品档案批量导入评分库；按标题去重，封面走站内 uploads 流程（自动生成 400/800 宽 webp 缩略图） |
| `backfill_meta.py` | 按「标题 → 别名 → 译名」归一化匹配，回填 platform / release_year / series |
| `dedup_games.py` | 合并重复条目（中英文异名、`∀`/`A`、间隔号、副标题差异等），评分与标签安全迁移 |
| `build_library_thumbs.py` | 给资料库封面生成 400px webp 缩略图。列表页原图直出时第 1 页 45 张就有 1.9 MB，压完降到 0.75 MB |
| `build_icons.py` | 从 `tools/vendor/lucide.min.js`（540 KB 全量包）裁剪出站点实际用到的 56 个图标，产出 13 KB 的 `app/static/js/icons.js` |

> 数据脚本都支持 `--dry-run` / `--report`，建议先预览再执行。
>
> `lucide.min.js` 是图标生成的**输入源**，不在 Web 根目录下，也不会被任何页面加载——线上只用裁剪后的 `icons.js`（13 KB / gzip 4 KB）。

---

## 目录结构概览

- `app/`：应用代码（FastAPI、模型、路由、模板、静态资源等）  
- `app/data/library.json`：资料库的示例数据（898 部作品的元数据），可直接替换  
- `tools/`：数据导入 / 回填 / 查重 / 缩略图 / 图标生成脚本  
- `alembic/`：数据库迁移脚本  
- `deploy.sh`：一键部署 / 更新 / 卸载脚本  
- `env.example`：环境变量模板  
- `requirements.txt`：Python 依赖列表  
- `stg_website.service`：Systemd 服务单元模板  
- `Caddyfile`：Caddy 反向代理模板（HTTPS / HTTP 配置）  
- `gunicorn_config.py`：Gunicorn 配置  
- `DEPLOYMENT.md`：更详细的部署说明与故障排查  

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

本项目已经托管在 GitHub 仓库 [`vihithr/FastAPI-Game-Rating-Lite`](https://github.com/vihithr/FastAPI-Game-Rating-Lite.git)，根据你的登录方式分两种常见场景：

#### 2.1 常见场景：以普通用户登录，使用 `sudo`（真正一行一键）

**有域名（HTTPS 模式，自动申请证书）**：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
  install --from-github https://github.com/vihithr/FastAPI-Game-Rating-Lite.git --domain example.com
```

**无域名（IP 模式，仅 HTTP，用于内网 / 临时环境）**：

```bash
sudo bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
  install --from-github https://github.com/vihithr/FastAPI-Game-Rating-Lite.git --ip
```

> 说明：这里用的是 `bash <(curl ...)`，脚本从网络加载，但 **stdin 仍然是你的终端**，所以交互式向导（数据库类型 / 域名选择等）可以正常工作，不会像 `curl ... | bash` 那样直接读到 EOF 退出。

#### 2.2 直接以 `root` 登录（无 `sudo` 或最小系统环境）

如果你登录的就是 `root@server`，或者系统里没有安装 `sudo`，请使用下列命令（**去掉 sudo**）：

**有域名（HTTPS 模式）**：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
  install --from-github https://github.com/vihithr/FastAPI-Game-Rating-Lite.git --domain example.com
```

**无域名（IP 模式）**：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh) \
  install --from-github https://github.com/vihithr/FastAPI-Game-Rating-Lite.git --ip
```

常用可选参数（可与上面的命令组合使用）：

- `--branch <name>`：指定分支，默认为 `main`  
- `--force`：跳过卸载 / 静态清理时的二次确认（请谨慎使用）  

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

---

## 数据来源与版权

`app/data/library.json` 是 STG 资料库的示例数据，元数据采集自
[shmups.wiki](https://shmups.wiki)、Arcade Database (ADB/MAME)、Steam 商店 API 与
日 / 英维基百科，采集于 2026-10。其中作品简介为各来源原文的短摘录（维基部分遵循 CC BY-SA），
**版权归原作者所有**，本项目仅作资料整理与检索用途。

**封面图片不随仓库分发**（`app/static/library/covers/` 已在 `.gitignore` 中）。
封面版权归各发行商所有，如需完整封面请自行整理并放入该目录，再运行
`tools/build_library_thumbs.py` 生成缩略图。

### 多语言

`library.json` 里每条记录的 `desc` 是采集到的**原文**（英文或日文），`lang` 是自动判定的语种。
非中文条目额外带一个 `zh_desc` 字段，是**机器翻译**的中文简介（435 条）。

详情页会按浏览器的 `Accept-Language` **自动选默认语言**：中文浏览器看中文译文，
英/日文浏览器看原文；右上角保留「中文 / English / 日本語」切换作为手动覆盖。
页面上标注了「中文简介由机器翻译」。

语种判定要同时避开两个坑：

- 英文简介里夹日文原名（`1941: カウンターアタック is a vertically scrolling…`）——只看「有没有假名」会误判成日文
- 中文简介里夹英文专有名词（`Team Shanghai Alice 发布的同人射击作品`）——只看「拉丁字母占比」会误判成英文，这类文本拉丁字母能占到七成

所以规则是**先看汉字/假名占比，再看拉丁字母**：汉字+假名 ≥ 4 个字符且占比 ≥ 25% 判为中文/日文
（假名占其中 > 10% 则判日文），否则拉丁字母 > 70% 判英文，其余归中文。



如果你要替换示例数据，覆盖 `app/data/library.json` 即可，字段含义见 `tools/import_library.py` 顶部注释。

