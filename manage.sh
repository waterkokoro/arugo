#!/bin/bash

# AI Agent 应用管理脚本
# 用法: ./manage.sh [start|stop|restart|log|status]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# PID 文件
BACKEND_PID_FILE="$SCRIPT_DIR/.backend.pid"
FRONTEND_PID_FILE="$SCRIPT_DIR/.frontend.pid"
SHADOW_PID_FILE="$SCRIPT_DIR/.shadow.pid"

# 日志文件
BACKEND_LOG="$SCRIPT_DIR/logs/backend.log"
FRONTEND_LOG="$SCRIPT_DIR/logs/frontend.log"
SHADOW_LOG="$SCRIPT_DIR/logs/shadow.log"

# 确保日志目录存在
mkdir -p "$SCRIPT_DIR/logs"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取后端 PID
get_backend_pid() {
    if [ -f "$BACKEND_PID_FILE" ]; then
        cat "$BACKEND_PID_FILE"
    else
        echo ""
    fi
}

# 获取前端 PID
get_frontend_pid() {
    if [ -f "$FRONTEND_PID_FILE" ]; then
        cat "$FRONTEND_PID_FILE"
    else
        echo ""
    fi
}

# 检查进程是否运行
is_running() {
    local pid=$1
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    return 1
}

# 清理端口占用
kill_port() {
    local port=$1
    local pid=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
        print_warn "端口 $port 被占用 (PID: $pid)，正在清理..."
        kill -9 $pid 2>/dev/null || true
        sleep 1
    fi
}

# 启动后端
start_backend() {
    local pid=$(get_backend_pid)
    if is_running "$pid"; then
        print_warn "后端已在运行 (PID: $pid)"
        return 0
    fi

    # 清理端口
    kill_port 8000

    print_info "启动后端服务..."
    cd "$BACKEND_DIR"

    # 检查虚拟环境
    if [ ! -d "venv" ]; then
        print_info "创建 Python 虚拟环境..."
        python3 -m venv venv
    fi

    # 安装依赖
    print_info "检查 Python 依赖..."
    ./venv/bin/pip install -q -r requirements.txt 2>/dev/null || true

    # 启动服务
    nohup ./venv/bin/python main.py > "$BACKEND_LOG" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"

    sleep 2
    if is_running "$(get_backend_pid)"; then
        print_info "后端启动成功 (PID: $(get_backend_pid), 端口: 8000)"
    else
        print_error "后端启动失败，请查看日志: $BACKEND_LOG"
        rm -f "$BACKEND_PID_FILE"
        return 1
    fi
}

# 启动前端
start_frontend() {
    local pid=$(get_frontend_pid)
    if is_running "$pid"; then
        print_warn "前端已在运行 (PID: $pid)"
        return 0
    fi

    # 清理端口
    kill_port 5173

    print_info "启动前端服务..."
    cd "$FRONTEND_DIR"

    # 检查依赖
    if [ ! -d "node_modules" ]; then
        print_info "安装前端依赖..."
        npm install --silent
    fi

    # 启动服务（直接用 npx vite 避免 npm 父进程 PID 不匹配问题）
    nohup npx vite > "$FRONTEND_LOG" 2>&1 &
    echo $! > "$FRONTEND_PID_FILE"

    sleep 3
    if is_running "$(get_frontend_pid)"; then
        print_info "前端启动成功 (PID: $(get_frontend_pid), 端口: 5173)"
    else
        print_error "前端启动失败，请查看日志: $FRONTEND_LOG"
        rm -f "$FRONTEND_PID_FILE"
        return 1
    fi
}

# 停止后端
stop_backend() {
    local pid=$(get_backend_pid)
    if is_running "$pid"; then
        print_info "停止后端服务 (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        # 如果还在运行，强制杀死
        if is_running "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$BACKEND_PID_FILE"
        print_info "后端已停止"
    else
        print_warn "后端未在运行"
        rm -f "$BACKEND_PID_FILE"
    fi
}

# 停止前端
stop_frontend() {
    local pid=$(get_frontend_pid)
    if is_running "$pid"; then
        print_info "停止前端服务 (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        if is_running "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$FRONTEND_PID_FILE"
        print_info "前端已停止"
    else
        print_warn "前端未在运行"
        rm -f "$FRONTEND_PID_FILE"
    fi
}

# 启动所有服务
cmd_start() {
    print_info "=========================================="
    print_info "      启动 AI Agent 应用"
    print_info "=========================================="
    start_backend
    start_frontend
    echo ""
    echo -e "${GREEN}==========================================${NC}"
    echo -e "${GREEN}  应用已启动！${NC}"
    echo -e "${GREEN}==========================================${NC}"
    echo ""
    echo -e "  ${GREEN}前端地址:${NC}  http://localhost:5173"
    echo -e "  ${GREEN}后端地址:${NC}  http://localhost:8000"
    echo -e "  ${GREEN}API文档:${NC}   http://localhost:8000/docs"
    echo ""
    echo -e "${GREEN}==========================================${NC}"
    echo ""
}

# 停止所有服务
cmd_stop() {
    print_info "=========================================="
    print_info "      停止 AI Agent 应用"
    print_info "=========================================="
    stop_frontend
    stop_backend
    print_info "所有服务已停止"
}

# 重启所有服务
cmd_restart() {
    cmd_stop
    sleep 1
    cmd_start
}

# 查看状态
cmd_status() {
    echo ""
    print_info "=========================================="
    print_info "      AI Agent 应用状态"
    print_info "=========================================="

    local backend_pid=$(get_backend_pid)
    local frontend_pid=$(get_frontend_pid)

    if is_running "$backend_pid"; then
        echo -e "  后端: ${GREEN}运行中${NC} (PID: $backend_pid, 端口: 8000)"
    else
        echo -e "  后端: ${RED}已停止${NC}"
    fi

    if is_running "$frontend_pid"; then
        echo -e "  前端: ${GREEN}运行中${NC} (PID: $frontend_pid, 端口: 5173)"
    else
        echo -e "  前端: ${RED}已停止${NC}"
    fi

    shadow_status

    echo ""
}

# 查看日志
cmd_log() {
    local service=${1:-all}

    case "$service" in
        backend|be)
            if [ -f "$BACKEND_LOG" ]; then
                tail -f "$BACKEND_LOG"
            else
                print_warn "后端日志文件不存在"
            fi
            ;;
        frontend|fe)
            if [ -f "$FRONTEND_LOG" ]; then
                tail -f "$FRONTEND_LOG"
            else
                print_warn "前端日志文件不存在"
            fi
            ;;
        all|"")
            print_info "后端日志 ($BACKEND_LOG):"
            echo "----------------------------------------"
            tail -20 "$BACKEND_LOG" 2>/dev/null || echo "(无日志)"
            echo ""
            print_info "前端日志 ($FRONTEND_LOG):"
            echo "----------------------------------------"
            tail -20 "$FRONTEND_LOG" 2>/dev/null || echo "(无日志)"
            ;;
        *)
            print_error "未知服务: $service"
            echo "用法: $0 log [backend|frontend|all]"
            exit 1
            ;;
    esac
}

# 显示帮助
show_help() {
    echo ""
    echo "AI Agent 应用管理脚本"
    echo ""
    echo "用法: $0 <command> [options]"
    echo ""
    echo "命令:"
    echo "  start      启动所有服务"
    echo "  stop       停止所有服务"
    echo "  restart    重启所有服务"
    echo "  status     查看服务状态"
    echo "  log        查看日志 (最近20行)"
    echo "  log be     实时查看后端日志"
    echo "  log fe     实时查看前端日志"
    echo "  help       显示帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 start       # 启动应用"
    echo "  $0 stop        # 停止应用"
    echo "  $0 log be      # 查看后端日志"
    echo ""
}

# ============================================
# 影子服务管理 (B 服务 - 8001 端口)
# ============================================

# 获取影子 PID
get_shadow_pid() {
    if [ -f "$SHADOW_PID_FILE" ]; then
        cat "$SHADOW_PID_FILE"
    else
        echo ""
    fi
}

# 启动影子服务
start_shadow() {
    local pid=$(get_shadow_pid)
    if is_running "$pid"; then
        print_warn "影子服务已在运行 (PID: $pid)"
        return 0
    fi

    # 清理端口
    kill_port 8001

    print_info "启动影子服务 B (端口 8001)..."
    cd "$BACKEND_DIR"

    # 使用虚拟环境启动，设置 ARUGO_SHADOW 环境变量
    ARUGO_SHADOW=true nohup ./venv/bin/python -c "
import os
os.environ['ARUGO_SHADOW'] = 'true'
import uvicorn
uvicorn.run('main:app', host='0.0.0.0', port=8001, reload=False)
" > "$SHADOW_LOG" 2>&1 &
    echo $! > "$SHADOW_PID_FILE"

    sleep 3
    if is_running "$(get_shadow_pid)"; then
        print_info "影子服务 B 启动成功 (PID: $(get_shadow_pid), 端口: 8001) 🔷"
    else
        print_error "影子服务启动失败，请查看日志: $SHADOW_LOG"
        rm -f "$SHADOW_PID_FILE"
        return 1
    fi
}

# 停止影子服务
stop_shadow() {
    local pid=$(get_shadow_pid)
    if is_running "$pid"; then
        print_info "停止影子服务 B (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        if is_running "$pid"; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$SHADOW_PID_FILE"
        print_info "影子服务 B 已停止 🔷"
    else
        print_warn "影子服务未在运行"
        rm -f "$SHADOW_PID_FILE"
    fi
}

# 查看影子服务状态
shadow_status() {
    local shadow_pid=$(get_shadow_pid)

    if is_running "$shadow_pid"; then
        echo -e "  影子服务 B: ${GREEN}运行中${NC} (PID: $shadow_pid, 端口: 8001) 🔷"
    else
        echo -e "  影子服务 B: ${RED}已停止${NC} 🔷"
    fi
}

# ============================================

# 主入口
case "${1:-help}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    status)
        cmd_status
        ;;
    start-shadow)
        start_shadow
        ;;
    stop-shadow)
        stop_shadow
        ;;
    restart-shadow)
        stop_shadow
        sleep 1
        start_shadow
        ;;
    shadow-status)
        shadow_status
        ;;
    log)
        cmd_log "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "未知命令: $1"
        show_help
        exit 1
        ;;
esac
