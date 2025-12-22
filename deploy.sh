#!/bin/bash
# STG 社区网站一键部署脚本
# 支持安装和卸载功能，所有文件集中管理

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # 无颜色

# 配置项
PROJECT_NAME="stg_website"
INSTALL_DIR="/opt/${PROJECT_NAME}"
CADDY_DIR="${INSTALL_DIR}/caddy"  # Caddy 集中安装目录
SERVICE_USER="stg_website"
SERVICE_GROUP="stg_website"
# 如果未设置 STG_DOMAIN 环境变量，则使用空字符串（表示使用 IP 访问）
DOMAIN="${STG_DOMAIN:-}"
PYTHON_VERSION="3.8"
USE_IP_MODE=false  # 是否使用 IP 模式
PUBLIC_IP=""  # 公网 IP 地址
# 部署源相关
CODE_SOURCE="local"        # local | github | archive
GITHUB_REPO=""             # 当 CODE_SOURCE=github 时需要
GITHUB_BRANCH="main"
ARCHIVE_PATH=""            # 当 CODE_SOURCE=archive 时需要
# 交互控制
FORCE=false                # 跳过危险操作确认

# 函数定义
print_info() {
    echo -e "${GREEN}[信息]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[警告]${NC} $1"
}

print_error() {
    echo -e "${RED}[错误]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[步骤]${NC} $1"
}

# 从已安装环境中加载现有配置（域名 / IP 模式），避免每次重复输入
load_existing_config() {
    # 如果通过命令行参数或环境变量已经显式设置了 DOMAIN，则尊重该值
    if [ -n "${DOMAIN:-}" ]; then
        USE_IP_MODE=false
        return
    fi

    local ENV_FILE_PATH="$INSTALL_DIR/.env"
    if [ -f "$ENV_FILE_PATH" ]; then
        # 优先从 STG_DOMAIN 读取
        local ENV_DOMAIN
        ENV_DOMAIN=$(grep "^STG_DOMAIN=" "$ENV_FILE_PATH" 2>/dev/null | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')
        if [ -n "$ENV_DOMAIN" ]; then
            DOMAIN="$ENV_DOMAIN"
            USE_IP_MODE=false
            return
        fi

        # 其次根据 STG_SITE_BASE_URL 推断
        local SITE_URL
        SITE_URL=$(grep "^STG_SITE_BASE_URL=" "$ENV_FILE_PATH" 2>/dev/null | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')
        if echo "$SITE_URL" | grep -q "^https://"; then
            DOMAIN=$(echo "$SITE_URL" | sed -E 's#^https?://([^/]+)/?.*#\1#')
            USE_IP_MODE=false
            return
        elif echo "$SITE_URL" | grep -q "^http://"; then
            # 认为是 IP 模式
            USE_IP_MODE=true
            PUBLIC_IP=$(echo "$SITE_URL" | sed -E 's#^http://([^/:]+)/?.*#\1#')
            return
        fi
    fi
}

print_usage() {
    cat << EOF
用法: $0 [menu|install|uninstall] [选项]

子命令:
  menu                  交互式菜单（默认）
  install               安装 / 更新
  uninstall             卸载
  backup                备份当前安装（代码 + 数据库 + 上传文件，过滤环境数据）

常用选项:
  --domain <域名>       指定域名（使用 HTTPS 模式）
  --ip                  强制使用 IP 模式（HTTP）
  --from-github <repo>  从 GitHub 仓库拉取代码（需提供仓库地址）
  --branch <branch>     搭配 --from-github 指定分支，默认 main
  --from-local          使用当前脚本所在目录作为代码源（默认行为）
  --from-archive <file> 使用本地压缩包作为代码源（支持 .tar.gz/.tgz/.zip）
  --force               跳过危险操作的确认提示（卸载、静态清理）
  -h, --help            显示本帮助

示例:
  # GitHub 一键部署（HTTPS）
  curl -fsSL https://raw.githubusercontent.com/vihithr/FastAPI-Game-Rating-Lite/main/deploy.sh | \\
    bash -s -- install --from-github https://github.com/vihithr/FastAPI-Game-Rating-Lite.git --domain example.com

  # 本地压缩包部署（离线）
  ./deploy.sh install --from-archive stg_website.tar.gz --ip
EOF
}

# 备份排除列表（用于 tar 命令，格式为 --exclude=pattern）
get_backup_exclude_patterns() {
    # Python 相关缓存
    echo "--exclude=venv"
    echo "--exclude=__pycache__"
    echo "--exclude=*.pyc"
    echo "--exclude=*.pyo"
    echo "--exclude=*.pyd"
    # 配置文件（环境相关）
    echo "--exclude=.env"
    # 日志文件
    echo "--exclude=*.log"
    echo "--exclude=logs"
    echo "--exclude=log"
    # 临时文件
    echo "--exclude=*.tmp"
    echo "--exclude=*.temp"
    echo "--exclude=tmp"
    echo "--exclude=temp"
    # 缓存
    echo "--exclude=.cache"
    echo "--exclude=cache"
    echo "--exclude=*.cache"
    # 系统文件
    echo "--exclude=*.pid"
    echo "--exclude=*.lock"
    echo "--exclude=.DS_Store"
    echo "--exclude=Thumbs.db"
    # IDE / 版本控制
    echo "--exclude=.idea"
    echo "--exclude=.vscode"
    echo "--exclude=.git"
    echo "--exclude=.svn"
    echo "--exclude=*.swp"
    echo "--exclude=*.swo"
    # 运行时文件
    echo "--exclude=caddy"
}

parse_args() {
    COMMAND="menu"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            install|uninstall|menu|backup)
                COMMAND="$1"
                shift
                ;;
            --domain)
                DOMAIN="$2"
                export STG_DOMAIN="$2"
                shift 2
                ;;
            --ip)
                USE_IP_MODE=true
                DOMAIN=""
                export STG_DOMAIN=""
                shift
                ;;
            --from-github)
                CODE_SOURCE="github"
                # 可选地接受仓库地址
                if [[ -n "${2:-}" && ! "$2" =~ ^- ]]; then
                    GITHUB_REPO="$2"
                    shift 2
                else
                    shift
                fi
                ;;
            --branch)
                GITHUB_BRANCH="$2"
                shift 2
                ;;
            --from-local)
                CODE_SOURCE="local"
                shift
                ;;
            --from-archive)
                CODE_SOURCE="archive"
                ARCHIVE_PATH="$2"
                shift 2
                ;;
            --force|--yes)
                FORCE=true
                shift
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            *)
                print_warn "未知参数: $1"
                shift
                ;;
        esac
    done
}

# 获取公网 IP 地址
get_public_ip() {
    # 尝试多个服务获取公网 IP
    PUBLIC_IP=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
                curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
                curl -s --max-time 5 https://icanhazip.com 2>/dev/null || \
                curl -s --max-time 5 https://api.ip.sb/ip 2>/dev/null || \
                echo "")
    
    if [ -z "$PUBLIC_IP" ]; then
        # 如果都失败，尝试从网络接口获取
        PUBLIC_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' || \
                   hostname -I 2>/dev/null | awk '{print $1}' || \
                   echo "")
    fi
    
    echo "$PUBLIC_IP"
}

# 获取公网 IP 地址
get_public_ip() {
    # 尝试多个服务获取公网 IP
    PUBLIC_IP=$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || \
                curl -s --max-time 5 https://ifconfig.me 2>/dev/null || \
                curl -s --max-time 5 https://icanhazip.com 2>/dev/null || \
                curl -s --max-time 5 https://api.ip.sb/ip 2>/dev/null || \
                echo "")
    
    if [ -z "$PUBLIC_IP" ]; then
        # 如果都失败，尝试从网络接口获取
        PUBLIC_IP=$(ip route get 8.8.8.8 2>/dev/null | grep -oP 'src \K\S+' || \
                   hostname -I 2>/dev/null | awk '{print $1}' || \
                   echo "")
    fi
    
    echo "$PUBLIC_IP"
}

# 检测是否可以使用 sudo 或已经是 root
check_sudo() {
    if [ "$EUID" -eq 0 ]; then
        # 已经是 root，不需要 sudo
        USE_SUDO=""
        return 0
    elif command -v sudo &> /dev/null; then
        # 可以使用 sudo
        USE_SUDO="sudo"
        return 0
    else
        # 既不是 root 也没有 sudo
        return 1
    fi
}

# 以指定用户身份运行命令（自动检测 sudo）
run_as_user() {
    local user="$1"
    shift
    local cmd="$@"
    local exit_code=0
    
    if [ "$EUID" -eq 0 ]; then
        # 已经是 root，直接使用 su 或 runuser
        if command -v runuser &> /dev/null; then
            runuser -u "$user" -- bash -c "$cmd" || exit_code=$?
        else
            su -s /bin/bash "$user" -c "$cmd" || exit_code=$?
        fi
    elif command -v sudo &> /dev/null; then
        # 使用 sudo
        sudo -u "$user" bash -c "$cmd" || exit_code=$?
    else
        print_error "无法以用户 $user 身份运行命令（需要 root 权限或 sudo）"
        exit 1
    fi
    
    return $exit_code
}

check_root() {
    if [ "$EUID" -ne 0 ] && ! command -v sudo &> /dev/null; then 
        print_error "请使用 root 权限运行此脚本（使用 sudo 或以 root 用户运行）"
        exit 1
    fi
}

# -------------------------
# 应用服务管理辅助函数
# -------------------------

app_service_is_active() {
    systemctl is-active --quiet "${PROJECT_NAME}.service"
}

app_service_start() {
    if app_service_is_active; then
        print_info "检测到服务已在运行，执行重启以加载最新代码..."
        systemctl restart "${PROJECT_NAME}.service" || {
            print_error "服务重启失败，请检查日志: journalctl -u ${PROJECT_NAME}.service -n 50"
            return 1
        }
    else
        print_info "启动服务..."
        systemctl start "${PROJECT_NAME}.service" || {
            print_error "服务启动失败，请检查日志: journalctl -u ${PROJECT_NAME}.service -n 50"
            return 1
        }
    fi
}

app_service_stop() {
    print_info "停止服务..."
    systemctl stop "${PROJECT_NAME}.service" 2>/dev/null || {
        print_warn "停止服务时出现问题（可能本就未运行）"
    }
}

app_service_restart() {
    print_info "重启服务..."
    systemctl restart "${PROJECT_NAME}.service" || {
        print_error "服务重启失败，请检查日志: journalctl -u ${PROJECT_NAME}.service -n 50"
        return 1
    }
}

app_service_status() {
    systemctl status "${PROJECT_NAME}.service"
}

# 检测并安装系统包（显示详细输出）
install_system_package() {
    local package="$1"
    local package_name="$2"  # 可选：显示名称
    
    if [ -z "$package_name" ]; then
        package_name="$package"
    fi
    
    # 检测包管理器
    if command -v apt-get &> /dev/null; then
        # Debian/Ubuntu
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q "install ok installed"; then
            print_info "$package_name 已安装，跳过 ✓"
            return 0  # 已安装
        fi
        
        print_info "正在安装 $package_name..."
        export DEBIAN_FRONTEND=noninteractive
        print_info "更新软件包列表..."
        apt-get update || {
            print_error "更新软件包列表失败"
            return 1
        }
        print_info "安装 $package_name（显示详细输出）..."
        apt-get install -y "$package" || {
            print_error "安装 $package_name 失败"
            return 1
        }
        print_info "$package_name 安装完成 ✓"
        return 0
    elif command -v yum &> /dev/null; then
        # CentOS/RHEL
        if yum list installed "$package" &> /dev/null; then
            print_info "$package_name 已安装，跳过 ✓"
            return 0  # 已安装
        fi
        
        print_info "正在安装 $package_name..."
        print_info "安装 $package_name（显示详细输出）..."
        yum install -y "$package" || {
            print_error "安装 $package_name 失败"
            return 1
        }
        print_info "$package_name 安装完成 ✓"
        return 0
    elif command -v dnf &> /dev/null; then
        # Fedora
        if dnf list installed "$package" &> /dev/null; then
            print_info "$package_name 已安装，跳过 ✓"
            return 0  # 已安装
        fi
        
        print_info "正在安装 $package_name..."
        print_info "安装 $package_name（显示详细输出）..."
        dnf install -y "$package" || {
            print_error "安装 $package_name 失败"
            return 1
        }
        print_info "$package_name 安装完成 ✓"
        return 0
    else
        print_warn "未检测到支持的包管理器（apt/yum/dnf），无法自动安装 $package_name"
        return 1
    fi
}

check_dependencies() {
    print_step "检查系统依赖..."
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "未检测到 Python 3，请先安装 Python 3.8 或更高版本"
        exit 1
    fi
    
    PYTHON_VER=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    if [ "$(printf '%s\n' "$PYTHON_VERSION" "$PYTHON_VER" | sort -V | head -n1)" != "$PYTHON_VERSION" ]; then
        print_error "Python 版本必须 >= $PYTHON_VERSION，当前版本: $PYTHON_VER"
        exit 1
    fi
    
    print_info "Python 版本: $PYTHON_VER ✓"
    
    # 检查 python3-venv 模块
    if ! python3 -m venv --help &> /dev/null; then
        print_warn "Python venv 模块不可用，尝试自动安装..."
        
        # 根据 Python 版本确定包名
        PYTHON_MAJOR_MINOR=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        
        # 尝试安装对应的 venv 包
        if command -v apt-get &> /dev/null; then
            # Debian/Ubuntu: python3.x-venv
            VENV_PACKAGE="python${PYTHON_MAJOR_MINOR}-venv"
            if ! install_system_package "$VENV_PACKAGE" "python3-venv"; then
                # 如果特定版本失败，尝试通用包
                install_system_package "python3-venv" "python3-venv" || {
                    print_error "无法安装 python3-venv，请手动安装: apt install python${PYTHON_MAJOR_MINOR}-venv"
                    exit 1
                }
            fi
        elif command -v yum &> /dev/null || command -v dnf &> /dev/null; then
            # CentOS/RHEL/Fedora: python3-venv 或 python3x-venv
            VENV_PACKAGE="python${PYTHON_MAJOR_MINOR}-venv"
            if ! install_system_package "$VENV_PACKAGE" "python3-venv"; then
                install_system_package "python3-venv" "python3-venv" || {
                    print_error "无法安装 python3-venv，请手动安装"
                    exit 1
                }
            fi
        else
            print_error "无法自动安装 python3-venv，请手动安装后重试"
            exit 1
        fi
        
        # 再次检查
        if ! python3 -m venv --help &> /dev/null; then
            print_error "安装 python3-venv 后仍无法使用，请检查安装"
            exit 1
        fi
    fi
    print_info "Python venv 模块可用 ✓"
    
    # 检查邮件服务（Postfix 或 Sendmail），如果不存在则自动安装
    MAIL_SERVICE=""
    if systemctl is-active --quiet postfix 2>/dev/null || command -v postfix &> /dev/null; then
        MAIL_SERVICE="postfix"
        print_info "检测到 Postfix 邮件服务 ✓"
    elif systemctl is-active --quiet sendmail 2>/dev/null || command -v sendmail &> /dev/null; then
        MAIL_SERVICE="sendmail"
        print_info "检测到 Sendmail 邮件服务 ✓"
    else
        print_warn "未检测到邮件服务（Postfix/Sendmail），密码重置功能可能无法使用"
        print_info "尝试自动安装 Postfix 邮件服务..."
        
        if install_system_package "postfix" "Postfix 邮件服务"; then
            MAIL_SERVICE="postfix"
            print_info "Postfix 邮件服务已安装 ✓"
            print_info "注意：Postfix 需要配置才能正常发送邮件，默认配置可能仅支持本地发送"
            print_info "如需配置外部邮件服务器，请编辑 /etc/postfix/main.cf"
        else
            print_warn "Postfix 安装失败，邮件功能可能无法使用"
            print_warn "您可以稍后手动安装: apt install postfix 或 yum install postfix"
        fi
    fi
}

install_caddy() {
    print_step "安装 Caddy 反向代理服务器（集中安装到 ${CADDY_DIR}）..."
    
    # 创建 Caddy 安装目录
    mkdir -p "$CADDY_DIR"
    
    # 检测架构
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) CADDY_ARCH="amd64" ;;
        aarch64|arm64) CADDY_ARCH="arm64" ;;
        armv7l) CADDY_ARCH="armv7" ;;
        *) print_error "不支持的架构: $ARCH"; return 1 ;;
    esac
    
    # 获取最新版本
    print_info "获取 Caddy 最新版本..."
    CADDY_VERSION=$(curl -s https://api.github.com/repos/caddyserver/caddy/releases/latest | grep -oP '"tag_name": "\K[^"]+' | head -1)
    if [ -z "$CADDY_VERSION" ]; then
        CADDY_VERSION="v2.10.2"  # 使用已知版本作为后备
        print_warn "无法获取最新版本，使用默认版本: $CADDY_VERSION"
    fi
    
    # 移除版本号中的 'v' 前缀（如果存在）用于下载 URL
    CADDY_VERSION_NUM=$(echo "$CADDY_VERSION" | sed 's/^v//')
    
    print_info "下载 Caddy $CADDY_VERSION ($CADDY_ARCH)..."
    
    # 下载并安装到集中目录
    # Caddy v2 的下载 URL 格式（注意：版本号不带 'v' 前缀）
    CADDY_URL="https://github.com/caddyserver/caddy/releases/download/${CADDY_VERSION}/caddy_${CADDY_VERSION_NUM}_linux_${CADDY_ARCH}.tar.gz"
    
    cd "$CADDY_DIR"
    print_info "正在下载 Caddy（显示进度）..."
    
    # 下载文件并检查 HTTP 状态码
    HTTP_CODE=$(curl -L --write-out "%{http_code}" --progress-bar "$CADDY_URL" -o caddy.tar.gz)
    
    if [ "$HTTP_CODE" != "200" ]; then
        print_error "下载 Caddy 失败，HTTP 状态码: $HTTP_CODE"
        print_info "尝试使用备用下载方法（直接下载二进制文件）..."
        # 尝试直接下载二进制文件（如果 tar.gz 不可用）
        # 注意：二进制文件的 URL 格式可能不同
        CADDY_BINARY_URL="https://github.com/caddyserver/caddy/releases/download/${CADDY_VERSION}/caddy_${CADDY_VERSION_NUM}_linux_${CADDY_ARCH}"
        rm -f caddy.tar.gz
        HTTP_CODE=$(curl -L --write-out "%{http_code}" --progress-bar "$CADDY_BINARY_URL" -o caddy)
        if [ "$HTTP_CODE" = "200" ] && [ -f "caddy" ] && [ -s "caddy" ]; then
            chmod +x caddy
            print_info "Caddy 二进制文件下载成功 ✓"
        else
            print_error "备用下载方法也失败，HTTP 状态码: $HTTP_CODE"
            print_info "尝试使用官方安装脚本..."
            # 最后尝试：使用官方安装脚本
            if curl -fsSL https://getcaddy.com | bash -s personal; then
                if [ -f "/usr/local/bin/caddy" ]; then
                    cp /usr/local/bin/caddy "${CADDY_DIR}/caddy"
                    print_info "使用官方安装脚本安装 Caddy 成功 ✓"
                else
                    print_error "官方安装脚本执行失败"
                    return 1
                fi
            else
                print_error "所有 Caddy 下载方法都失败"
                print_error "请手动下载 Caddy: https://caddyserver.com/download"
                return 1
            fi
        fi
    else
        # 检查下载的文件是否是有效的 tar.gz 文件
        if ! file caddy.tar.gz | grep -q "gzip\|tar archive"; then
            print_warn "下载的文件可能不是有效的 tar.gz 文件，检查文件类型..."
            FILE_TYPE=$(file -b caddy.tar.gz)
            print_info "文件类型: $FILE_TYPE"
            
            # 如果文件是 HTML（可能是错误页面），尝试备用方法
            if echo "$FILE_TYPE" | grep -qi "html\|text"; then
                print_warn "下载的文件似乎是 HTML 错误页面，尝试备用下载方法..."
                rm -f caddy.tar.gz
                CADDY_BINARY_URL="https://github.com/caddyserver/caddy/releases/download/${CADDY_VERSION}/caddy_${CADDY_VERSION_NUM}_linux_${CADDY_ARCH}"
                HTTP_CODE=$(curl -L --write-out "%{http_code}" --progress-bar "$CADDY_BINARY_URL" -o caddy)
                if [ "$HTTP_CODE" = "200" ] && [ -f "caddy" ] && [ -s "caddy" ]; then
                    chmod +x caddy
                    print_info "Caddy 二进制文件下载成功 ✓"
                else
                    print_error "备用下载方法失败，HTTP 状态码: $HTTP_CODE"
                    print_info "尝试使用官方安装脚本..."
                    if curl -fsSL https://getcaddy.com | bash -s personal; then
                        if [ -f "/usr/local/bin/caddy" ]; then
                            cp /usr/local/bin/caddy "${CADDY_DIR}/caddy"
                            print_info "使用官方安装脚本安装 Caddy 成功 ✓"
                        else
                            print_error "官方安装脚本执行失败"
                            return 1
                        fi
                    else
                        print_error "所有 Caddy 下载方法都失败"
                        print_error "请手动下载 Caddy: https://caddyserver.com/download"
                        return 1
                    fi
                fi
            else
                print_error "下载的文件格式不正确: $FILE_TYPE"
                return 1
            fi
        else
            # 文件格式正确，解压
            print_info "解压 Caddy..."
            tar -xzf caddy.tar.gz || {
                print_error "解压 Caddy 失败"
                return 1
            }
            chmod +x caddy
            rm -f caddy.tar.gz LICENSE README.md 2>/dev/null || true
        fi
    fi
    
    # 创建符号链接到系统路径（便于使用）
    ln -sf "${CADDY_DIR}/caddy" /usr/local/bin/caddy
    
    # 创建 systemd 服务文件（使用 root 用户，不需要 caddy 用户）
    if [ ! -f /etc/systemd/system/caddy.service ]; then
        cat > /etc/systemd/system/caddy.service << EOF
[Unit]
Description=Caddy Web Server
Documentation=https://caddyserver.com/docs/
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
ExecStart=${CADDY_DIR}/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=${CADDY_DIR}/caddy reload --config /etc/caddy/Caddyfile --force
TimeoutStopSec=5s
LimitNOFILE=1048576
LimitNPROC=512
PrivateTmp=true
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
EOF
        
        # 创建配置目录
        mkdir -p /etc/caddy
        
        systemctl daemon-reload
    fi
    
    # 设置所有权
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$CADDY_DIR"
    
    print_info "Caddy 安装完成（安装位置: ${CADDY_DIR}）✓"
}

create_user() {
    print_step "创建服务用户和组（权限隔离）..."
    
    # 创建组
    if ! getent group "$SERVICE_GROUP" > /dev/null 2>&1; then
        groupadd -r "$SERVICE_GROUP"
        print_info "已创建组: $SERVICE_GROUP"
    else
        print_info "组 $SERVICE_GROUP 已存在 ✓"
    fi
    
    # 创建用户
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -g "$SERVICE_GROUP" -s /bin/false -d "$INSTALL_DIR" -c "STG 网站服务用户" "$SERVICE_USER"
        print_info "已创建用户: $SERVICE_USER"
    else
        print_info "用户 $SERVICE_USER 已存在 ✓"
    fi
}

sync_code() {
    print_step "同步应用代码到: $INSTALL_DIR"
    
    local source_dir=""
    local temp_dir=""
    
    case "$CODE_SOURCE" in
        github)
            if [ -z "$GITHUB_REPO" ]; then
                print_error "未提供 GitHub 仓库地址，请使用 --from-github <repo>"
                exit 1
            fi
            if ! command -v git &> /dev/null; then
                print_error "未找到 git，请先安装 git 再使用 --from-github"
                exit 1
            fi
            temp_dir="$(mktemp -d)"
            print_info "从 GitHub 拉取代码: $GITHUB_REPO (branch: $GITHUB_BRANCH)"
            if ! git clone --depth 1 --branch "$GITHUB_BRANCH" "$GITHUB_REPO" "$temp_dir"; then
                print_error "Git 克隆失败，请检查仓库地址/分支是否存在"
                rm -rf "$temp_dir" 2>/dev/null || true
                exit 1
            fi
            if [ -d "$temp_dir/vote_site" ]; then
                source_dir="$temp_dir/vote_site"
            else
                source_dir="$temp_dir"
            fi
            ;;
        archive)
            if [ -z "$ARCHIVE_PATH" ]; then
                print_error "未提供压缩包路径，请使用 --from-archive <file>"
                exit 1
            fi
            if [ ! -f "$ARCHIVE_PATH" ]; then
                print_error "压缩包不存在: $ARCHIVE_PATH"
                exit 1
            fi
            temp_dir="$(mktemp -d)"
            print_info "解压压缩包: $ARCHIVE_PATH"
            case "$ARCHIVE_PATH" in
                *.tar.gz|*.tgz|*.tar)
                    if ! tar -xf "$ARCHIVE_PATH" -C "$temp_dir"; then
                        print_error "解压失败，请确认文件格式为 tar/tgz"
                        rm -rf "$temp_dir" 2>/dev/null || true
                        exit 1
                    fi
                    ;;
                *.zip)
                    if ! command -v unzip &> /dev/null; then
                        print_error "未找到 unzip，请安装后再使用 .zip 包"
                        rm -rf "$temp_dir" 2>/dev/null || true
                        exit 1
                    fi
                    if ! unzip -q "$ARCHIVE_PATH" -d "$temp_dir"; then
                        print_error "解压 zip 失败，请检查文件"
                        rm -rf "$temp_dir" 2>/dev/null || true
                        exit 1
                    fi
                    ;;
                *)
                    print_error "不支持的压缩包格式，仅支持 .tar.gz/.tgz/.tar/.zip"
                    rm -rf "$temp_dir" 2>/dev/null || true
                    exit 1
                    ;;
            esac
            source_dir=$(find "$temp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
            if [ -z "$source_dir" ]; then
                source_dir="$temp_dir"
            fi
            if [ -d "$source_dir/vote_site" ]; then
                source_dir="$source_dir/vote_site"
            fi
            ;;
        *)
            source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            ;;
    esac
    
    # 创建安装目录
    mkdir -p "$INSTALL_DIR"
    
    # 复制所有文件（排除不必要的文件）
    print_info "复制应用文件..."
    
    # 检查目标位置是否已有数据库文件（用于判断是首次安装还是更新）
    local EXISTING_DB=""
    if [ -f "$INSTALL_DIR/stg_website.db" ]; then
        EXISTING_DB="$INSTALL_DIR/stg_website.db"
        print_info "检测到现有数据库文件，将在更新时保留它"
    fi
    
    if command -v rsync &> /dev/null; then
        print_info "使用 rsync 复制文件（显示详细输出）..."
        # 更新时排除数据库文件，避免覆盖现有数据
        # 但如果是首次安装（目标位置没有数据库），则允许从源目录拷贝数据库
        if [ -n "$EXISTING_DB" ]; then
            # 已有数据库，排除 .db 文件以保护现有数据
            rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
                --exclude='venv' --exclude='*.db' --exclude='copy_files.py' \
                "$source_dir/" "$INSTALL_DIR/"
            print_info "已保留现有数据库文件: $EXISTING_DB"
        else
            # 首次安装，允许拷贝数据库文件（如果源目录有的话）
            rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
                --exclude='venv' --exclude='copy_files.py' \
                "$source_dir/" "$INSTALL_DIR/"
            print_info "首次安装，已同步所有文件（包括数据库文件，如果存在）"
        fi
    else
        # 如果没有 rsync，使用 cp
        print_info "使用 cp 复制文件..."
        if [ -n "$EXISTING_DB" ]; then
            # 已有数据库，先备份，然后拷贝，最后恢复
            local DB_BACKUP="${EXISTING_DB}.backup.$$"
            cp "$EXISTING_DB" "$DB_BACKUP"
            cp -rv "$source_dir"/* "$INSTALL_DIR/" 2>&1 || true
            mv "$DB_BACKUP" "$EXISTING_DB"
            print_info "已保留现有数据库文件: $EXISTING_DB"
        else
            cp -rv "$source_dir"/* "$INSTALL_DIR/" 2>&1 || true
            print_info "首次安装，已同步所有文件（包括数据库文件，如果存在）"
        fi
        # 清理不需要的文件
        print_info "清理临时文件..."
        find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>&1 || true
        find "$INSTALL_DIR" -name "*.pyc" -delete 2>&1 || true
    fi
    
    # 设置所有权
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR"
    
    # 设置文件权限（目录 755，文件 644）
    find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
    find "$INSTALL_DIR" -type f -exec chmod 644 {} \;
    # 确保 Caddy 二进制保持可执行（避免被上面的 644 覆盖）
    if [ -f "$CADDY_DIR/caddy" ]; then
        chmod +x "$CADDY_DIR/caddy"
    fi
    
    # 特别处理数据库文件权限（如果存在）
    if [ -f "$INSTALL_DIR/stg_website.db" ]; then
        chmod 600 "$INSTALL_DIR/stg_website.db"
        chown "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/stg_website.db"
        print_info "已设置数据库文件权限: $INSTALL_DIR/stg_website.db"
    fi
    
    # 使脚本可执行
    chmod +x "$INSTALL_DIR/deploy.sh" 2>/dev/null || true
    
    # 清理临时目录（如有）
    if [ -n "$temp_dir" ] && [ -d "$temp_dir" ] && [ "$temp_dir" != "/" ]; then
        rm -rf "$temp_dir" 2>/dev/null || true
    fi
    
    print_info "代码同步完成 ✓"
}

setup_venv() {
    print_step "设置 Python 虚拟环境..."
    
    cd "$INSTALL_DIR"
    
    # 检查虚拟环境是否完整
    VENV_VALID=false
    if [ -d "venv" ]; then
        # 检查关键文件是否存在：activate 脚本和 Python 解释器
        if [ -f "venv/bin/activate" ] && ([ -f "venv/bin/python3" ] || [ -f "venv/bin/python" ]); then
            VENV_VALID=true
        fi
    fi
    
    # 如果虚拟环境不存在或不完整，创建或重建
    if [ "$VENV_VALID" = false ]; then
        if [ -d "venv" ]; then
            print_warn "检测到不完整的虚拟环境，正在删除并重新创建..."
            rm -rf venv
        fi
        
        # 先检查并安装 python3-venv 包（主动检查，避免创建时失败）
        print_info "检查 python3-venv 支持..."
        if ! python3 -c "import ensurepip" 2>/dev/null; then
            print_warn "检测到缺少 ensurepip 模块，尝试安装 python3-venv 包..."
            
            # 获取 Python 版本
            PYTHON_MAJOR_MINOR=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
            
            # 尝试安装对应的 venv 包
            if command -v apt-get &> /dev/null; then
                # Debian/Ubuntu: python3.x-venv
                VENV_PACKAGE="python${PYTHON_MAJOR_MINOR}-venv"
                if ! install_system_package "$VENV_PACKAGE" "python3-venv"; then
                    # 如果特定版本失败，尝试通用包
                    install_system_package "python3-venv" "python3-venv" || {
                        print_error "无法安装 python3-venv，请手动安装: apt install python${PYTHON_MAJOR_MINOR}-venv"
                        exit 1
                    }
                fi
            elif command -v yum &> /dev/null || command -v dnf &> /dev/null; then
                # CentOS/RHEL/Fedora
                VENV_PACKAGE="python${PYTHON_MAJOR_MINOR}-venv"
                if ! install_system_package "$VENV_PACKAGE" "python3-venv"; then
                    install_system_package "python3-venv" "python3-venv" || {
                        print_error "无法安装 python3-venv，请手动安装"
                        exit 1
                    }
                fi
            else
                print_error "无法自动安装 python3-venv，请手动安装后重试"
                exit 1
            fi
            
            # 再次检查 ensurepip
            if ! python3 -c "import ensurepip" 2>/dev/null; then
                print_warn "安装后 ensurepip 仍不可用，但继续尝试创建虚拟环境..."
            else
                print_info "python3-venv 支持已安装 ✓"
            fi
        else
            print_info "python3-venv 支持已就绪 ✓"
        fi
        
        # 创建虚拟环境（当前目录已经是 $INSTALL_DIR）
        print_info "创建虚拟环境..."
        VENV_OUTPUT=$(run_as_user "$SERVICE_USER" "python3 -m venv venv" 2>&1)
        VENV_EXIT=$?
        
        if [ $VENV_EXIT -eq 0 ]; then
            # 验证虚拟环境是否创建成功
            if [ -f "venv/bin/activate" ]; then
                print_info "虚拟环境已创建 ✓"
                # 立即设置权限，确保可执行文件有执行权限
                print_info "设置虚拟环境权限..."
                chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/venv"
                find "$INSTALL_DIR/venv/bin" -type f -exec chmod +x {} \; 2>/dev/null || true
            else
                print_error "虚拟环境创建后验证失败，激活脚本不存在"
                exit 1
            fi
        else
            # 如果创建失败，显示详细错误
            print_error "虚拟环境创建失败"
            if [ -n "$VENV_OUTPUT" ]; then
                echo "$VENV_OUTPUT"
            fi
            
            # 检查是否是 ensurepip 问题
            if echo "$VENV_OUTPUT" | grep -qi "ensurepip\|python.*venv"; then
                print_error "检测到 ensurepip 问题，但已尝试安装 python3-venv 包"
                print_error "请手动检查: apt list --installed | grep python.*venv"
            fi
            
            print_error "请手动运行以下命令进行诊断:"
            print_error "  cd $INSTALL_DIR"
            print_error "  python3 -m venv venv"
            exit 1
        fi
    else
        print_info "虚拟环境已存在且完整，跳过创建 ✓"
    fi
    
    # 验证虚拟环境可用性
    if [ ! -f "venv/bin/activate" ]; then
        print_error "虚拟环境验证失败，激活脚本不存在"
        exit 1
    fi
    
    # 确保虚拟环境权限正确（无论是否是新创建的）
    print_info "检查并修复虚拟环境权限..."
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/venv"
    # 确保所有可执行文件有执行权限
    find "$INSTALL_DIR/venv" -type f -name "python*" -exec chmod +x {} \; 2>/dev/null || true
    find "$INSTALL_DIR/venv" -type f -name "pip*" -exec chmod +x {} \; 2>/dev/null || true
    find "$INSTALL_DIR/venv/bin" -type f -exec chmod +x {} \; 2>/dev/null || true
    print_info "虚拟环境权限已修复 ✓"
    
    # 验证权限是否正确
    if [ ! -x "venv/bin/pip" ] && [ ! -x "venv/bin/pip3" ]; then
        print_warn "pip 可执行文件权限可能有问题，尝试修复..."
        chmod +x venv/bin/pip* 2>/dev/null || true
        chmod +x venv/bin/python* 2>/dev/null || true
    fi
    
    # 升级 pip（显示详细输出）
    print_info "升级 pip、setuptools 和 wheel..."
    print_info "pip 升级输出："
    run_as_user "$SERVICE_USER" "source venv/bin/activate && pip install --upgrade pip setuptools wheel" || {
        print_warn "pip 升级失败，但继续执行..."
    }
    
    # 安装依赖（显示详细输出）
    if [ -f "requirements.txt" ]; then
        print_info "安装 Python 依赖包（这可能需要几分钟，显示详细输出）..."
        print_info "pip 安装输出："
        run_as_user "$SERVICE_USER" "source venv/bin/activate && pip install -r requirements.txt" || {
            print_error "依赖安装失败，请检查网络连接和 requirements.txt"
            print_error "如果遇到权限问题，请检查虚拟环境文件权限"
            exit 1
        }
        print_info "Python 依赖安装完成 ✓"
    else
        print_error "未找到 requirements.txt"
        exit 1
    fi
}

setup_env_file() {
    print_step "配置环境变量..."
    
    ENV_FILE="$INSTALL_DIR/.env"
    ENV_EXAMPLE="$INSTALL_DIR/env.example"
    
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            print_info "已从模板创建 .env 文件"
        else
            print_warn "未找到 env.example，创建最小配置 .env 文件"
            touch "$ENV_FILE"
        fi
        
        # 自动生成安全密钥
        if command -v python3 &> /dev/null; then
            print_info "自动生成安全密钥..."
            SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null)
            SESSION_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null)
            
            if [ -n "$SECRET_KEY" ] && [ -n "$SESSION_KEY" ]; then
                # 更新或添加密钥
                if grep -q "STG_SECRET_KEY=" "$ENV_FILE"; then
                    sed -i "s|STG_SECRET_KEY=.*|STG_SECRET_KEY=$SECRET_KEY|" "$ENV_FILE"
                else
                    echo "STG_SECRET_KEY=$SECRET_KEY" >> "$ENV_FILE"
                fi
                
                if grep -q "STG_SESSION_SECRET_KEY=" "$ENV_FILE"; then
                    sed -i "s|STG_SESSION_SECRET_KEY=.*|STG_SESSION_SECRET_KEY=$SESSION_KEY|" "$ENV_FILE"
                else
                    echo "STG_SESSION_SECRET_KEY=$SESSION_KEY" >> "$ENV_FILE"
                fi
                
                print_info "安全密钥已自动生成 ✓"
            fi
            
            # 设置数据库URL（强制使用 SQLite，使用绝对路径）
            DB_FILE_PATH="$INSTALL_DIR/stg_website.db"
            DATABASE_URL="sqlite:///$DB_FILE_PATH"
            if ! grep -q "STG_DATABASE_URL=" "$ENV_FILE" || grep -q "^STG_DATABASE_URL=$" "$ENV_FILE"; then
                if grep -q "STG_DATABASE_URL=" "$ENV_FILE"; then
                    sed -i "s|^STG_DATABASE_URL=.*|STG_DATABASE_URL=$DATABASE_URL|" "$ENV_FILE"
                else
                    echo "STG_DATABASE_URL=$DATABASE_URL" >> "$ENV_FILE"
                fi
                print_info "数据库URL已设置为 SQLite: $DATABASE_URL"
            else
                # 如果已存在但不是 SQLite，也强制设置为 SQLite
                CURRENT_DB=$(grep "^STG_DATABASE_URL=" "$ENV_FILE" | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
                if [ -z "$CURRENT_DB" ] || [ "$CURRENT_DB" = "" ] || ! echo "$CURRENT_DB" | grep -q "^sqlite"; then
                    sed -i "s|^STG_DATABASE_URL=.*|STG_DATABASE_URL=$DATABASE_URL|" "$ENV_FILE"
                    print_info "已强制设置为 SQLite: $DATABASE_URL"
                fi
            fi
        fi
        
        print_warn "环境变量文件已创建，请根据需要编辑: $ENV_FILE"
    else
        print_info ".env 文件已存在，跳过创建"
    fi
    
    # 无论是新建还是已有 .env，都根据当前域名 / IP 模式更新访问相关配置
    update_env_domain_settings "$ENV_FILE"
    
    # 设置安全权限（仅所有者可读）
    chmod 600 "$ENV_FILE"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$ENV_FILE"
    
    print_info "环境变量配置完成 ✓"
}

setup_upload_directories() {
    print_step "设置上传目录..."
    
    # 创建上传目录
    mkdir -p "$INSTALL_DIR/app/static/uploads/articles"
    mkdir -p "$INSTALL_DIR/app/static/uploads/covers"
    
    # 设置所有权和权限
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_DIR/app/static/uploads"
    chmod -R 755 "$INSTALL_DIR/app/static/uploads"
    
    print_info "上传目录配置完成 ✓"
}

static_cleanup() {
    print_step "静态资源清理（文章静态包 + 封面图片）..."

    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "安装目录不存在: $INSTALL_DIR，请先完成安装。"
        return 1
    fi

    if [ ! -d "$INSTALL_DIR/venv" ]; then
        print_error "未找到虚拟环境 $INSTALL_DIR/venv，请先通过安装/更新流程创建。"
        return 1
    fi

    echo ""
    print_info "第一步：预览（dry-run），不会真正删除任何文件，只打印即将被删除的对象。"
    echo ""

    local PY_CMD_DRY="from app.maintenance.cleanup_static import cleanup_covers, cleanup_article_statics; cleanup_covers(dry_run=True); cleanup_article_statics(dry_run=True)"
    run_as_user "$SERVICE_USER" "cd '$INSTALL_DIR' && source venv/bin/activate && python3 -c \"$PY_CMD_DRY\"" || {
        print_error "dry-run 预览执行失败，请检查应用代码与依赖是否完整。"
        return 1
    }

    if [ "$FORCE" = false ]; then
        echo ""
        read -p "是否继续执行实际删除（不可恢复）？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "已取消实际删除，仅执行了 dry-run 预览。"
            return 0
        fi
    else
        print_warn "已开启 --force，跳过确认，直接执行实际删除。"
    fi

    print_warn "即将执行实际删除，请确保已做好备份！"
    local PY_CMD_REAL="from app.maintenance.cleanup_static import cleanup_covers, cleanup_article_statics; cleanup_covers(dry_run=False); cleanup_article_statics(dry_run=False)"
    run_as_user "$SERVICE_USER" "cd '$INSTALL_DIR' && source venv/bin/activate && python3 -c \"$PY_CMD_REAL\"" || {
        print_error "实际删除执行过程中出现错误，请检查输出信息。"
        return 1
    }

    print_info "静态资源清理完成。"
}

backup() {
    print_step "开始备份 STG 社区网站..."

    # 检查安装目录
    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "安装目录不存在: $INSTALL_DIR"
        print_error "请先完成安装后再执行备份。"
        return 1
    fi

    # 生成备份文件名
    local TIMESTAMP
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S" 2>/dev/null || echo "backup")
    local BACKUP_NAME="${PROJECT_NAME}_backup_${TIMESTAMP}.tar.gz"

    # 默认备份目录为安装目录的父目录
    local BACKUP_DIR
    BACKUP_DIR=$(dirname "$INSTALL_DIR")
    local BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

    echo ""
    read -p "备份文件将保存到: $BACKUP_PATH (直接回车使用默认路径，或输入自定义路径): " USER_BACKUP_PATH
    if [ -n "$USER_BACKUP_PATH" ]; then
        BACKUP_PATH="$USER_BACKUP_PATH"
        # 如果只输入了文件名，则放在默认目录
        if [ "$(dirname "$BACKUP_PATH")" = "." ] || [ "$(dirname "$BACKUP_PATH")" = "$BACKUP_PATH" ]; then
            BACKUP_PATH="${BACKUP_DIR}/${BACKUP_PATH}"
        fi
    fi

    # 确保备份目录存在
    local BACKUP_DIR_PATH
    BACKUP_DIR_PATH=$(dirname "$BACKUP_PATH")
    if [ ! -d "$BACKUP_DIR_PATH" ]; then
        print_info "创建备份目录: $BACKUP_DIR_PATH"
        mkdir -p "$BACKUP_DIR_PATH" || {
            print_error "无法创建备份目录: $BACKUP_DIR_PATH"
            return 1
        }
    fi

    # 检查备份文件是否已存在
    if [ -f "$BACKUP_PATH" ]; then
        print_warn "备份文件已存在: $BACKUP_PATH"
        read -p "是否覆盖？(y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "取消备份"
            return 0
        fi
        rm -f "$BACKUP_PATH"
    fi

    print_info "正在创建备份..."
    print_info "源目录: $INSTALL_DIR"
    print_info "备份文件: $BACKUP_PATH"
    print_info "将排除虚拟环境、日志、缓存、.env 等环境相关文件，仅保留代码、数据库和上传资源。"

    # 切换到安装目录的父目录
    cd "$(dirname "$INSTALL_DIR")" || {
        print_error "无法切换到目录: $(dirname "$INSTALL_DIR")"
        return 1
    }

    local INSTALL_BASENAME
    INSTALL_BASENAME=$(basename "$INSTALL_DIR")

    # 构建排除参数
    local EXCLUDE_ARGS=()
    while IFS= read -r exclude_pattern; do
        EXCLUDE_ARGS+=("$exclude_pattern")
    done < <(get_backup_exclude_patterns)

    # 创建压缩包
    if ! tar -czf "$BACKUP_PATH" "${EXCLUDE_ARGS[@]}" "$INSTALL_BASENAME" 2>/dev/null; then
        print_error "备份失败，请检查磁盘空间和权限，以及 tar 命令是否可用。"
        return 1
    fi

    # 验证备份文件
    if [ ! -f "$BACKUP_PATH" ]; then
        print_error "备份文件创建失败。"
        return 1
    fi

    # 获取备份大小
    local BACKUP_SIZE
    if command -v du &> /dev/null; then
        BACKUP_SIZE=$(du -h "$BACKUP_PATH" | cut -f1)
    else
        BACKUP_SIZE="未知"
    fi

    print_info "备份完成！✓"
    echo ""
    print_info "备份文件: $BACKUP_PATH"
    print_info "文件大小: $BACKUP_SIZE"
    echo ""
    print_info "在新服务器上恢复的基本步骤："
    print_info "  1. 将备份文件复制到目标服务器并解压，例如："
    echo "     tar -xzf $(basename "$BACKUP_PATH")"
    print_info "  2. 进入解压后的 ${INSTALL_BASENAME} 目录："
    echo "     cd ${INSTALL_BASENAME}"
    print_info "  3. 执行部署脚本进行安装 / 更新（会自动重建 venv、Caddy、.env 等环境）："
    echo "     ./deploy.sh install --from-local --ip"
    print_info "     或者：./deploy.sh install --from-local --domain your-domain.com"
    echo ""
    print_info "注意：备份中包含 SQLite 数据库和上传资源，可以直接迁移业务数据；环境变量和运行环境会在新机器上重新配置。"
}

setup_database() {
    print_step "初始化数据库..."
    
    cd "$INSTALL_DIR"
    
    # 检查 .env 文件是否存在
    if [ ! -f ".env" ]; then
        print_error ".env 文件不存在，请先运行环境变量配置"
        exit 1
    fi
    
    # 强制使用 SQLite 数据库（用户明确要求）
    print_info "配置 SQLite 数据库..."
    
    # 读取当前的数据库 URL（如果存在）
    CURRENT_DB_URL=$(grep "^STG_DATABASE_URL=" ".env" 2>/dev/null | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')
    
    # 如果当前配置不是 SQLite 或者是空的，强制设置为 SQLite
    if [ -z "$CURRENT_DB_URL" ] || [ "$CURRENT_DB_URL" = "" ] || ! echo "$CURRENT_DB_URL" | grep -q "^sqlite"; then
        # 使用绝对路径的 SQLite，避免工作目录问题
        DB_FILE_PATH="$INSTALL_DIR/stg_website.db"
        DATABASE_URL="sqlite:///$DB_FILE_PATH"
        
        print_info "设置 SQLite 数据库路径: $DB_FILE_PATH"
        
        if grep -q "^STG_DATABASE_URL=" ".env"; then
            # 替换现有的配置
            sed -i "s|^STG_DATABASE_URL=.*|STG_DATABASE_URL=$DATABASE_URL|" ".env"
        else
            # 添加新配置
            echo "STG_DATABASE_URL=$DATABASE_URL" >> ".env"
        fi
        print_info "数据库URL已设置为: $DATABASE_URL"
    else
        # 已经是 SQLite，但确保使用绝对路径
        if echo "$CURRENT_DB_URL" | grep -q "^sqlite:///\./"; then
            # 如果是相对路径，转换为绝对路径
            DB_FILE_PATH="$INSTALL_DIR/stg_website.db"
            DATABASE_URL="sqlite:///$DB_FILE_PATH"
            sed -i "s|^STG_DATABASE_URL=.*|STG_DATABASE_URL=$DATABASE_URL|" ".env"
            print_info "已将相对路径转换为绝对路径: $DATABASE_URL"
        else
            DATABASE_URL="$CURRENT_DB_URL"
            print_info "使用现有 SQLite 配置: $DATABASE_URL"
        fi
    fi
    
    # 直接从 .env 文件读取数据库 URL（最可靠的方法）
    STG_DATABASE_URL=$(grep "^STG_DATABASE_URL=" ".env" 2>/dev/null | cut -d'=' -f2- | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' -e 's/^["'\'']//' -e 's/["'\'']$//')
    
    # 验证读取到的值
    if [ -z "$STG_DATABASE_URL" ] || [ "$STG_DATABASE_URL" = "" ]; then
        print_error "无法从 .env 文件读取数据库 URL"
        print_error "尝试直接设置..."
        DB_FILE_PATH="$INSTALL_DIR/stg_website.db"
        STG_DATABASE_URL="sqlite:///$DB_FILE_PATH"
        echo "STG_DATABASE_URL=$STG_DATABASE_URL" >> ".env"
        print_info "已直接设置数据库 URL: $STG_DATABASE_URL"
    fi
    
    # 导出数据库 URL 并显示配置信息
    export STG_DATABASE_URL="$STG_DATABASE_URL"
    
    # 显示数据库配置（SQLite 显示完整路径）
    if echo "$STG_DATABASE_URL" | grep -q "^sqlite"; then
        # 提取 SQLite 文件路径用于显示
        DB_PATH=$(echo "$STG_DATABASE_URL" | sed 's|^sqlite:///||')
        print_info "使用 SQLite 数据库: $DB_PATH"
        print_info "数据库 URL: $STG_DATABASE_URL"
    else
        # 其他数据库类型，隐藏密码
        SAFE_URL=$(echo "$STG_DATABASE_URL" | sed 's/:[^:@]*@/:***@/')
        print_info "使用数据库: $SAFE_URL"
    fi
    
    # 验证 SQLite 数据库路径的目录是否存在
    if echo "$STG_DATABASE_URL" | grep -q "^sqlite"; then
        DB_PATH=$(echo "$STG_DATABASE_URL" | sed 's|^sqlite:///||')
        DB_DIR=$(dirname "$DB_PATH")
        if [ ! -d "$DB_DIR" ]; then
            print_info "创建数据库目录: $DB_DIR"
            mkdir -p "$DB_DIR"
            chown "$SERVICE_USER:$SERVICE_GROUP" "$DB_DIR"
        fi
        
        # 检查数据库文件是否已存在
        if [ -f "$DB_PATH" ]; then
            # 获取数据库文件大小
            DB_SIZE=$(stat -f%z "$DB_PATH" 2>/dev/null || stat -c%s "$DB_PATH" 2>/dev/null || echo "0")
            if [ "$DB_SIZE" -gt 0 ]; then
                print_info "检测到现有数据库文件: $DB_PATH (大小: ${DB_SIZE} 字节)"
                print_info "将保留现有数据库数据，仅更新表结构（如果需要）"
                DB_EXISTS=true
            else
                print_warn "数据库文件存在但为空，将重新初始化"
                DB_EXISTS=false
            fi
        else
            print_info "数据库文件不存在，将创建新数据库"
            DB_EXISTS=false
        fi
    else
        DB_EXISTS=false
    fi
    
    # 初始化数据库表
    if [ "$DB_EXISTS" = true ]; then
        print_info "更新数据库表结构（保留现有数据）..."
    else
        print_info "创建数据库表..."
    fi
    print_info "正在执行数据库初始化（这可能需要几秒钟）..."
    
    # 准备环境变量字符串
    ENV_VARS=""
    if [ -n "$STG_DATABASE_URL" ]; then
        ENV_VARS="export STG_DATABASE_URL='$STG_DATABASE_URL'; "
    fi
    
    # 临时禁用 set -e 以便更好地处理错误
    set +e
    
    # 直接调用 run_as_user（数据库初始化通常很快，不需要 timeout）
    # 如果确实需要超时保护，可以在 Python 代码层面实现
    print_info "执行数据库初始化命令..."
    DB_OUTPUT=$(run_as_user "$SERVICE_USER" "cd '$INSTALL_DIR' && $ENV_VARS source venv/bin/activate && python3 -c 'from app import models, database; models.Base.metadata.create_all(bind=database.engine)'" 2>&1)
    DB_EXIT=$?
    
    # 重新启用 set -e
    set -e
    
    if [ $DB_EXIT -ne 0 ]; then
        print_error "数据库初始化失败（退出码: $DB_EXIT）"
        if [ -n "$DB_OUTPUT" ]; then
            echo "错误输出:"
            echo "$DB_OUTPUT"
        else
            print_warn "没有错误输出，可能是权限或环境问题"
        fi
        print_error "请检查："
        print_error "  1. .env 文件中的 STG_DATABASE_URL 配置是否正确"
        print_error "  2. 数据库文件路径是否有写权限"
        print_error "  3. 如果使用 PostgreSQL/MySQL，请确保数据库服务正在运行"
        print_error "  4. 检查虚拟环境中的依赖是否完整安装"
        print_error "  5. 尝试手动运行: cd $INSTALL_DIR && source venv/bin/activate && python3 -c 'from app import models, database; models.Base.metadata.create_all(bind=database.engine)'"
        exit 1
    else
        print_info "数据库表创建成功 ✓"
        # 显示输出（如果有）
        if [ -n "$DB_OUTPUT" ] && [ "$DB_OUTPUT" != "" ]; then
            echo "$DB_OUTPUT"
        fi
    fi
    
    # 初始化悬赏板块
    print_info "初始化悬赏板块..."
    set +e
    BOUNTY_OUTPUT=$(run_as_user "$SERVICE_USER" "cd '$INSTALL_DIR' && $ENV_VARS source venv/bin/activate && python3 -c 'from app.main import init_bounty_categories; init_bounty_categories()'" 2>&1)
    BOUNTY_EXIT=$?
    set -e
    
    if [ $BOUNTY_EXIT -eq 0 ]; then
        print_info "悬赏板块初始化完成 ✓"
        if [ -n "$BOUNTY_OUTPUT" ] && [ "$BOUNTY_OUTPUT" != "" ]; then
            echo "$BOUNTY_OUTPUT"
        fi
    else
        print_warn "悬赏板块初始化失败（退出码: $BOUNTY_EXIT），但可以继续"
        if [ -n "$BOUNTY_OUTPUT" ]; then
            echo "警告输出: $BOUNTY_OUTPUT"
        fi
    fi
    
    # 设置数据库文件权限
    if [ -f "stg_website.db" ]; then
        chmod 600 "stg_website.db"
        chown "$SERVICE_USER:$SERVICE_GROUP" "stg_website.db"
        print_info "数据库文件权限已设置 ✓"
    fi
    
    print_info "数据库初始化完成 ✓"
}

setup_systemd_service() {
    print_step "配置 Systemd 服务..."
    
    SERVICE_FILE="/etc/systemd/system/${PROJECT_NAME}.service"
    SERVICE_TEMPLATE="$INSTALL_DIR/${PROJECT_NAME}.service"
    
    if [ -f "$SERVICE_TEMPLATE" ]; then
        # 复制服务文件
        cp "$SERVICE_TEMPLATE" "$SERVICE_FILE"
        
        # 重新加载 systemd
        systemctl daemon-reload
        
        # 启用服务
        systemctl enable "${PROJECT_NAME}.service"
        
        print_info "Systemd 服务配置完成 ✓"
    else
        print_error "未找到服务模板文件: $SERVICE_TEMPLATE"
        exit 1
    fi
}

setup_caddy() {
    print_step "配置 Caddy 反向代理..."
    
    # 检查 Caddy 是否已安装
    if [ ! -f "${CADDY_DIR}/caddy" ]; then
        install_caddy
    fi
    
    CADDYFILE="/etc/caddy/Caddyfile"
    CADDYFILE_TEMPLATE="$INSTALL_DIR/Caddyfile"
    
    # 确保 /etc/caddy 目录存在
    if [ ! -d "/etc/caddy" ]; then
        print_info "创建 Caddy 配置目录..."
        mkdir -p /etc/caddy
    fi
    
    # 创建日志目录（如果 Caddyfile 中使用了日志）
    if [ ! -d "/var/log/caddy" ]; then
        print_info "创建 Caddy 日志目录..."
        mkdir -p /var/log/caddy
    fi
    
    if [ -f "$CADDYFILE_TEMPLATE" ]; then
        print_info "生成 Caddyfile 配置文件..."
        
        if [ "$USE_IP_MODE" = true ]; then
            # IP 模式：使用 HTTP，不使用 HTTPS
            print_info "使用 IP 模式配置（HTTP）..."
            cat > "$CADDYFILE" << EOF
# STG Community Website Caddyfile - IP Mode
# Using HTTP (no HTTPS) for IP access

:80 {
    # Reverse proxy to Gunicorn
    reverse_proxy 127.0.0.1:8000 {
        # Headers
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto http
    }
    
    # Enable compression
    encode gzip zstd
    
    # Security headers (without HSTS since we're using HTTP)
    header {
        # Prevent clickjacking
        X-Frame-Options "SAMEORIGIN"
        # XSS Protection
        X-Content-Type-Options "nosniff"
        # Referrer Policy
        Referrer-Policy "strict-origin-when-cross-origin"
    }
    
    # Logging
    log {
        output file /var/log/caddy/stg_website.log
        format json
    }
}
EOF
        else
            # 域名模式：使用 HTTPS
            print_info "使用域名模式配置（HTTPS）..."
            sed "s/vote.stgcaomenlibrary.top/$DOMAIN/g" "$CADDYFILE_TEMPLATE" > "$CADDYFILE"
        fi
        
        # 验证 Caddyfile
        if [ -f "${CADDY_DIR}/caddy" ]; then
            VALIDATE_OUTPUT=$("${CADDY_DIR}/caddy" validate --config "$CADDYFILE" 2>&1)
            VALIDATE_EXIT=$?
            if [ $VALIDATE_EXIT -eq 0 ]; then
                print_info "Caddyfile 验证通过 ✓"
                
                # 重新加载 Caddy
                systemctl reload caddy 2>/dev/null || systemctl restart caddy 2>/dev/null || true
                print_info "Caddy 配置已应用 ✓"
            else
                print_warn "Caddyfile 验证失败（退出码: $VALIDATE_EXIT）"
                if [ -n "$VALIDATE_OUTPUT" ]; then
                    echo "验证错误: $VALIDATE_OUTPUT"
                fi
                print_warn "但继续执行，Caddy 可能会在启动时报告错误..."
                print_info "您可以稍后手动验证: ${CADDY_DIR}/caddy validate --config $CADDYFILE"
                systemctl restart caddy 2>/dev/null || true
            fi
        else
            print_warn "Caddy 二进制文件不存在，跳过验证"
            print_warn "Caddyfile 已创建，但 Caddy 服务可能无法启动"
            print_warn "请检查 Caddy 安装是否成功"
        fi
    else
        print_warn "未找到 Caddyfile 模板，跳过 Caddy 配置"
    fi
}

start_services() {
    print_step "启动服务..."
    
    # 启动 / 重启 应用服务（如果已在运行则重启以加载最新代码）
    if ! app_service_start; then
        exit 1
    fi
    
    sleep 2
    
    # 检查服务状态
    if app_service_is_active; then
        print_info "应用服务运行正常 ✓"
    else
        print_warn "应用服务可能未正常运行，请检查: sudo systemctl status ${PROJECT_NAME}.service"
    fi
    
    # 确保 Caddy 运行
    if [ -f "${CADDY_DIR}/caddy" ]; then
        systemctl start caddy 2>/dev/null || true
    fi
    
    print_info "服务启动完成 ✓"
}

# 卸载函数
uninstall() {
    print_step "开始卸载 STG 社区网站..."
    
    # 确认
    if [ "$FORCE" = false ]; then
        read -p "确定要卸载吗？这将删除所有安装的文件和服务。 (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "取消卸载"
            exit 0
        fi
    else
        print_warn "已开启 --force，跳过卸载确认，默认继续。"
    fi
    
    # 停止服务
    print_info "停止服务..."
    systemctl stop "${PROJECT_NAME}.service" 2>/dev/null || true
    systemctl stop caddy 2>/dev/null || true
    
    # 禁用服务
    print_info "禁用服务..."
    systemctl disable "${PROJECT_NAME}.service" 2>/dev/null || true
    systemctl disable caddy 2>/dev/null || true
    
    # 删除服务文件
    print_info "删除服务文件..."
    rm -f "/etc/systemd/system/${PROJECT_NAME}.service"
    rm -f /etc/systemd/system/caddy.service
    systemctl daemon-reload
    
    # 删除 Caddy 符号链接
    rm -f /usr/local/bin/caddy
    
    # 删除 Caddy 配置文件（可选，保留用户数据）
    if [ "$FORCE" = false ]; then
        read -p "是否删除 Caddy 配置文件？ (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -f /etc/caddy/Caddyfile
        fi
    else
        print_warn "已开启 --force，删除 Caddy 配置文件。"
        rm -f /etc/caddy/Caddyfile
    fi
    
    # 删除安装目录（可选，保留用户数据）
    if [ "$FORCE" = false ]; then
        read -p "是否删除安装目录 ${INSTALL_DIR}？（这将删除所有数据，包括数据库） (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
            print_info "已删除安装目录: $INSTALL_DIR"
        else
            print_info "保留安装目录: $INSTALL_DIR"
        fi
    else
        print_warn "已开启 --force，删除安装目录和数据。"
        rm -rf "$INSTALL_DIR"
        print_info "已删除安装目录: $INSTALL_DIR"
    fi
    
    # 删除用户和组（可选）
    if [ "$FORCE" = false ]; then
        read -p "是否删除服务用户 ${SERVICE_USER} 和组 ${SERVICE_GROUP}？ (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            userdel "$SERVICE_USER" 2>/dev/null || true
            groupdel "$SERVICE_GROUP" 2>/dev/null || true
            print_info "已删除用户和组"
        else
            print_info "保留用户和组"
        fi
    else
        print_warn "已开启 --force，删除服务用户与组。"
        userdel "$SERVICE_USER" 2>/dev/null || true
        groupdel "$SERVICE_GROUP" 2>/dev/null || true
        print_info "已删除用户和组"
    fi
    
    print_info "卸载完成！"
}

print_summary() {
    echo ""
    print_info "=========================================="
    print_info "部署完成！"
    print_info "=========================================="
    echo ""
    print_info "安装目录: $INSTALL_DIR"
    print_info "Caddy 目录: $CADDY_DIR"
    print_info "服务用户: $SERVICE_USER"
    print_info "服务名称: ${PROJECT_NAME}.service"
    print_info "部署脚本: $INSTALL_DIR/deploy.sh（用于后续更新 / 管理）"
    
    if [ "$USE_IP_MODE" = true ]; then
        print_info "访问模式: IP 地址（HTTP）"
        if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "" ]; then
            print_info "访问地址: http://${PUBLIC_IP}:80"
            echo ""
            print_info "═══════════════════════════════════════"
            print_info "  网站访问地址: http://${PUBLIC_IP}"
            print_info "═══════════════════════════════════════"
        else
            print_warn "无法获取公网 IP，请手动检查服务器 IP 地址"
            print_info "本地访问: http://localhost:8000"
        fi
    else
        print_info "访问模式: 域名（HTTPS）"
        print_info "域名: $DOMAIN"
        echo ""
        print_info "═══════════════════════════════════════"
        print_info "  网站访问地址: https://${DOMAIN}"
        print_info "═══════════════════════════════════════"
    fi
    echo ""
    print_info "常用命令:"
    if [ "$EUID" -eq 0 ]; then
        echo "  - 查看日志: journalctl -u ${PROJECT_NAME}.service -f"
        echo "  - 重启服务: systemctl restart ${PROJECT_NAME}.service"
        echo "  - 查看状态: systemctl status ${PROJECT_NAME}.service"
        echo "  - 查看 Caddy 日志: journalctl -u caddy -f"
        echo "  - 编辑配置: nano $INSTALL_DIR/.env"
        echo "  - 进入部署管理菜单: $INSTALL_DIR/deploy.sh menu"
        echo "  - 卸载: $0 uninstall"
    else
        echo "  - 查看日志: sudo journalctl -u ${PROJECT_NAME}.service -f"
        echo "  - 重启服务: sudo systemctl restart ${PROJECT_NAME}.service"
        echo "  - 查看状态: sudo systemctl status ${PROJECT_NAME}.service"
        echo "  - 查看 Caddy 日志: sudo journalctl -u caddy -f"
        echo "  - 编辑配置: sudo nano $INSTALL_DIR/.env"
        echo "  - 进入部署管理菜单: sudo $INSTALL_DIR/deploy.sh menu"
        echo "  - 卸载: sudo $0 uninstall"
    fi
    echo ""
    print_warn "重要提示:"
    print_warn "  1. 请检查并更新 $INSTALL_DIR/.env 中的配置（如需要）"
    if [ "$USE_IP_MODE" = false ]; then
        print_warn "  2. 确保 DNS 已正确配置，将 $DOMAIN 指向此服务器"
        print_warn "  3. 如需设置管理员用户，运行:"
    else
        print_warn "  2. 当前使用 IP 模式，如需切换为域名，请在脚本菜单中选择“更改配置（域名 / IP 模式）”"
        print_warn "  3. 如需设置管理员用户，运行:"
    fi
    if [ "$EUID" -eq 0 ]; then
        if command -v runuser &> /dev/null; then
            echo "     runuser -u $SERVICE_USER -- bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python3 set_admin.py <用户名> true'"
        else
            echo "     su -s /bin/bash $SERVICE_USER -c 'cd $INSTALL_DIR && source venv/bin/activate && python3 set_admin.py <用户名> true'"
        fi
    else
        echo "     sudo -u $SERVICE_USER bash -c 'cd $INSTALL_DIR && source venv/bin/activate && python3 set_admin.py <用户名> true'"
    fi
    echo ""
    print_info "部署完成！网站应该已经可以访问了。"
}

interactive_install_settings() {
    echo ""
    print_step "安装 / 更新 配置向导"
    echo ""

    # 数据库类型（目前仅支持 SQLite，预留交互位）
    echo "数据库类型："
    echo "  1) SQLite（默认，当前仅支持）"
    read -p "请选择数据库类型 [1]: " DB_CHOICE
    DB_CHOICE=${DB_CHOICE:-1}
    case "$DB_CHOICE" in
        1|*)
            print_info "已选择 SQLite 数据库（当前脚本仅支持 SQLite）"
            ;;
    esac

    echo ""
    print_step "网站访问方式设置"
    echo ""

    # 根据当前变量推断默认模式（如果已有配置则优先使用）
    local DEFAULT_MODE="2"
    if [ -n "${DOMAIN:-}" ]; then
        DEFAULT_MODE="1"
    fi

    echo "访问方式："
    echo "  1) 使用域名（HTTPS）"
    echo "  2) 使用 IP 地址（HTTP）"
    read -p "请选择访问方式 [${DEFAULT_MODE}]: " MODE_CHOICE
    MODE_CHOICE=${MODE_CHOICE:-$DEFAULT_MODE}

    if [ "$MODE_CHOICE" = "1" ]; then
        read -p "请输入域名（当前: ${DOMAIN:-<未设置>}，直接回车保留当前）: " INPUT_DOMAIN
        if [ -n "$INPUT_DOMAIN" ]; then
            DOMAIN="$INPUT_DOMAIN"
        fi

        if [ -n "$DOMAIN" ]; then
            export STG_DOMAIN="$DOMAIN"
            USE_IP_MODE=false
            print_info "将使用域名模式: $DOMAIN（HTTPS）"
        else
            print_warn "未配置域名，将回退为 IP 模式（HTTP）"
            DOMAIN=""
            export STG_DOMAIN=""
            USE_IP_MODE=true
        fi
    else
        DOMAIN=""
        export STG_DOMAIN=""
        USE_IP_MODE=true
        print_info "将使用 IP 模式（HTTP）"
    fi
}

# 根据域名 / IP 模式更新 .env 中与访问地址相关的配置
update_env_domain_settings() {
    local ENV_FILE_PATH="$1"

    if [ ! -f "$ENV_FILE_PATH" ]; then
        return 0
    fi

    # 设置站点URL
    local SITE_URL=""
    if [ "$USE_IP_MODE" = true ]; then
        if [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "" ]; then
            PUBLIC_IP=$(get_public_ip)
        fi
        if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "" ]; then
            SITE_URL="http://${PUBLIC_IP}/"
        else
            SITE_URL="http://localhost:8000/"
        fi
    else
        if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "" ]; then
            SITE_URL="https://${DOMAIN}/"
        else
            # 如果没设置 DOMAIN，尝试主机名
            local HOSTNAME_VAL
            HOSTNAME_VAL=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "localhost")
            if [ "$HOSTNAME_VAL" != "localhost" ] && [ "$HOSTNAME_VAL" != "localhost.localdomain" ]; then
                if [ "$USE_IP_MODE" = true ]; then
                    SITE_URL="http://${HOSTNAME_VAL}/"
                else
                    SITE_URL="https://${HOSTNAME_VAL}/"
                fi
            else
                SITE_URL="http://localhost:8000/"
            fi
        fi
    fi

    if grep -q "STG_SITE_BASE_URL=" "$ENV_FILE_PATH"; then
        sed -i "s|STG_SITE_BASE_URL=.*|STG_SITE_BASE_URL=$SITE_URL|" "$ENV_FILE_PATH"
    else
        echo "STG_SITE_BASE_URL=$SITE_URL" >> "$ENV_FILE_PATH"
    fi
    print_info "站点URL已更新为: $SITE_URL"

    # 设置发件人地址
    local SENDER=""
    if [ -n "$DOMAIN" ] && [ "$DOMAIN" != "vote.stgcaomenlibrary.top" ]; then
        SENDER="noreply@${DOMAIN}"
    else
        local HOSTNAME_VAL
        HOSTNAME_VAL=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "localhost")
        if [ "$HOSTNAME_VAL" != "localhost" ] && [ "$HOSTNAME_VAL" != "localhost.localdomain" ]; then
            SENDER="noreply@${HOSTNAME_VAL}"
        else
            SENDER="noreply@localhost"
        fi
    fi

    if grep -q "STG_SENDER_ADDRESS=" "$ENV_FILE_PATH"; then
        sed -i "s|STG_SENDER_ADDRESS=.*|STG_SENDER_ADDRESS=$SENDER|" "$ENV_FILE_PATH"
    else
        echo "STG_SENDER_ADDRESS=$SENDER" >> "$ENV_FILE_PATH"
    fi
    print_info "发件人地址已更新为: $SENDER"

    # 设置 HTTPS 仅限（生产环境）
    if [ "$USE_IP_MODE" = true ]; then
        # IP 模式下默认不强制 HTTPS
        if grep -q "STG_HTTPS_ONLY=" "$ENV_FILE_PATH"; then
            sed -i "s|STG_HTTPS_ONLY=.*|STG_HTTPS_ONLY=false|" "$ENV_FILE_PATH"
        else
            echo "STG_HTTPS_ONLY=false" >> "$ENV_FILE_PATH"
        fi
    else
        if grep -q "STG_HTTPS_ONLY=" "$ENV_FILE_PATH"; then
            sed -i "s|STG_HTTPS_ONLY=.*|STG_HTTPS_ONLY=true|" "$ENV_FILE_PATH"
        else
            echo "STG_HTTPS_ONLY=true" >> "$ENV_FILE_PATH"
        fi
    fi
}

apply_config_changes() {
    print_step "应用配置变更..."

    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "安装目录不存在: $INSTALL_DIR，请先完成安装。"
        return 1
    fi

    local ENV_FILE_PATH="$INSTALL_DIR/.env"
    if [ ! -f "$ENV_FILE_PATH" ]; then
        print_warn ".env 文件不存在，将尝试创建基础配置..."
        setup_env_file
        ENV_FILE_PATH="$INSTALL_DIR/.env"
    fi

    # 更新 STG_DOMAIN（如果存在）
    if [ -n "$DOMAIN" ]; then
        if grep -q "^STG_DOMAIN=" "$ENV_FILE_PATH"; then
            sed -i "s|^STG_DOMAIN=.*|STG_DOMAIN=$DOMAIN|" "$ENV_FILE_PATH"
        else
            echo "STG_DOMAIN=$DOMAIN" >> "$ENV_FILE_PATH"
        fi
    else
        # 清理 STG_DOMAIN
        sed -i '/^STG_DOMAIN=/d' "$ENV_FILE_PATH" || true
    fi

    # 根据当前模式更新 URL / 发件人 / HTTPS ONLY
    update_env_domain_settings "$ENV_FILE_PATH"

    # 重新设置 .env 权限
    chmod 600 "$ENV_FILE_PATH"
    chown "$SERVICE_USER:$SERVICE_GROUP" "$ENV_FILE_PATH"

    # 更新 Caddy 配置（基于 DOMAIN / USE_IP_MODE）
    setup_caddy

    # 重启应用服务以应用新配置（如果服务已存在）
    if app_service_is_active; then
        app_service_restart || print_warn "应用服务重启失败，请手动检查。"
    fi

    print_info "配置变更已应用。"
}

change_config() {
    print_step "交互式更改配置（域名 / IP 模式）..."

    if [ ! -d "$INSTALL_DIR" ]; then
        print_warn "尚未检测到安装目录: $INSTALL_DIR，建议先执行安装 / 更新。"
    fi

    echo ""
    echo "当前访问模式："
    if [ -n "$DOMAIN" ]; then
        echo "  - 域名模式（HTTPS），当前域名: $DOMAIN"
    else
        echo "  - IP 模式（HTTP）"
    fi
    echo ""
    echo "1) 使用域名（HTTPS）"
    echo "2) 使用 IP 地址（HTTP）"
    read -p "请选择新的访问方式 [1/2]: " MODE_CHOICE

    case "$MODE_CHOICE" in
        1)
            read -p "请输入新的域名（留空则保留当前: ${DOMAIN:-<未设置>}）: " NEW_DOMAIN
            if [ -n "$NEW_DOMAIN" ]; then
                DOMAIN="$NEW_DOMAIN"
            fi
            if [ -z "$DOMAIN" ]; then
                print_error "未配置域名，无法切换到域名模式。"
                return 1
            fi
            USE_IP_MODE=false
            export STG_DOMAIN="$DOMAIN"
            print_info "已设置为域名模式: $DOMAIN（HTTPS）"
            ;;
        2)
            DOMAIN=""
            USE_IP_MODE=true
            export STG_DOMAIN=""
            print_info "已切换为 IP 模式（HTTP）"
            ;;
        *)
            print_warn "无效选择，保持当前配置不变。"
            return 0
            ;;
    esac

    # IP 模式下尝试更新公网 IP
    if [ "$USE_IP_MODE" = true ]; then
        print_info "正在获取公网 IP 地址..."
        PUBLIC_IP=$(get_public_ip)
        if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "" ]; then
            print_info "检测到公网 IP: $PUBLIC_IP"
        else
            print_warn "无法自动获取公网 IP，将使用本地 IP"
            PUBLIC_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
        fi
    fi

    # 应用变更（更新 .env / Caddy / 服务）
    apply_config_changes
}

show_current_config() {
    print_step "当前配置概览"
    print_info "安装目录: $INSTALL_DIR"
    print_info "服务名称: ${PROJECT_NAME}.service"

    if [ -n "$DOMAIN" ]; then
        print_info "访问模式: 域名（HTTPS）"
        print_info "当前域名: $DOMAIN"
    else
        print_info "访问模式: IP 地址（HTTP）"
        CURRENT_IP=$(get_public_ip)
        if [ -n "$CURRENT_IP" ]; then
            print_info "检测到公网 IP: $CURRENT_IP"
            print_info "预计访问地址: http://${CURRENT_IP}"
        else
            print_info "预计访问地址: http://<服务器IP>"
        fi
    fi

    # 数据库信息（从 .env 读取）
    local ENV_FILE_PATH="$INSTALL_DIR/.env"
    if [ -f "$ENV_FILE_PATH" ]; then
        local DB_URL
        DB_URL=$(grep "^STG_DATABASE_URL=" "$ENV_FILE_PATH" 2>/dev/null | cut -d'=' -f2- || echo "")
        if echo "$DB_URL" | grep -q "^sqlite"; then
            print_info "数据库类型: SQLite"
            local DB_PATH
            DB_PATH=$(echo "$DB_URL" | sed 's|^sqlite:///||')
            print_info "数据库路径: $DB_PATH"
        elif [ -n "$DB_URL" ]; then
            print_info "数据库 URL: $DB_URL"
        else
            print_warn "尚未在 .env 中配置 STG_DATABASE_URL"
        fi
    else
        print_warn "尚未找到 $ENV_FILE_PATH，可能尚未完成安装。"
    fi
}

# 主执行流程
install() {
    echo ""
    print_info "=========================================="
    print_info "STG 社区网站一键部署脚本"
    print_info "=========================================="
    echo ""

    # 交互式安装配置
    interactive_install_settings

    # 根据是否配置域名决定运行模式（结合交互结果）
    if [ -z "$DOMAIN" ] || [ "$DOMAIN" = "" ]; then
        USE_IP_MODE=true
        print_info "未配置域名，将使用 IP 地址模式（HTTP）"
        print_info "正在获取公网 IP 地址..."
        PUBLIC_IP=$(get_public_ip)
        if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "" ]; then
            print_info "检测到公网 IP: $PUBLIC_IP"
        else
            print_warn "无法自动获取公网 IP，将使用本地 IP"
            PUBLIC_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "127.0.0.1")
        fi
    else
        USE_IP_MODE=false
        print_info "使用域名模式: $DOMAIN"
    fi
    
    check_root
    check_dependencies
    create_user
    sync_code
    setup_venv
    setup_env_file
    setup_upload_directories
    setup_database
    setup_systemd_service
    setup_caddy
    start_services
    print_summary
}

# 显示主菜单
show_menu() {
    while true; do
        echo ""
        print_info "=========================================="
        print_info " STG 社区网站 管理脚本"
        print_info "=========================================="
        echo ""
        echo " 1) 安装 / 更新"
        echo " 2) 更改配置（域名 / IP 模式）"
        echo " 3) 查看配置"
        echo " 4) 运行管理（服务 / 日志 / 静态资源清理）"
        echo " 5) 卸载"
        echo " 6) 其他"
        echo " 7) 备份"
        echo " 8) 退出"
        echo ""
        read -p "请选择 [1-8]: " choice

        case "$choice" in
            1)
                echo ""
                print_step "开始安装 / 更新 STG 社区网站..."
                install
                ;;
            2)
                echo ""
                print_step "更改配置（域名 / IP 模式）..."
                change_config
                ;;
            3)
                echo ""
                print_step "查看当前配置..."
                show_current_config
                ;;
            4)
                echo ""
                print_step "运行管理..."
                echo " 1) 启动服务"
                echo " 2) 停止服务"
                echo " 3) 重启服务"
                echo " 4) 查看状态"
                echo " 5) 查看最近日志（应用）"
                echo " 6) 查看最近日志（Caddy）"
                echo " 7) 静态资源清理（清理无索引封面与文章静态包）"
                echo " 8) 返回上级菜单"
                read -p "请选择 [1-8]: " svc_choice
                case "$svc_choice" in
                    1)
                        if app_service_start; then
                            print_info "服务已启动或已重启 ✓"
                        fi
                        ;;
                    2)
                        app_service_stop
                        print_info "停止命令已执行（如服务在运行则已停止）"
                        ;;
                    3)
                        if app_service_restart; then
                            print_info "服务已重启 ✓"
                        fi
                        ;;
                    4)
                        app_service_status
                        ;;
                    5)
                        echo ""
                        print_step "查看应用最近 100 行日志..."
                        journalctl -u "${PROJECT_NAME}.service" -n 100 --no-pager || print_warn "无法读取日志（可能需要 root 或 sudo）"
                        ;;
                    6)
                        echo ""
                        print_step "查看 Caddy 最近 100 行日志..."
                        journalctl -u caddy -n 100 --no-pager || print_warn "无法读取 Caddy 日志（可能尚未安装或需要 root）"
                        ;;
                    7)
                        echo ""
                        print_step "静态资源清理（简单运维）..."
                        static_cleanup
                        ;;
                    *)
                        ;;
                esac
                ;;
            5)
                echo ""
                print_step "卸载 STG 社区网站..."
                check_root
                uninstall
                ;;
            6)
                echo ""
                print_step "其他"
                echo " - 您可以手动编辑 $INSTALL_DIR/.env 来调整高级配置"
                echo " - 如需查看日志，可使用: journalctl -u ${PROJECT_NAME}.service -f"
                echo " - 关于：STG 社区网站是一个用于 STG 游戏评价与社区交流的网站，脚本支持一键安装、配置和反向代理"
                ;;
            7)
                echo ""
                print_step "备份 STG 社区网站..."
                backup
                ;;
            8)
                echo ""
                print_info "已退出管理菜单。"
                break
                ;;
            *)
                echo ""
                print_warn "无效的选择，请输入 1-6 之间的数字。"
                ;;
        esac
    done
}

# 主函数：根据参数执行安装或卸载或进入菜单
main() {
    parse_args "$@"
    # 在处理子命令前，从已安装环境中加载现有配置，便于交互时使用默认值
    load_existing_config
    
    case "${COMMAND:-menu}" in
        menu)
            show_menu
            ;;
        install)
            install
            ;;
        uninstall)
            check_root
            uninstall
            ;;
        backup)
            backup
            ;;
        *)
            echo "用法: $0 [menu|install|uninstall]"
            echo ""
            echo "   menu      - 交互式管理菜单（默认）"
            echo "   install   - 直接安装 / 更新 STG 社区网站"
            echo "   uninstall - 卸载 STG 社区网站"
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
