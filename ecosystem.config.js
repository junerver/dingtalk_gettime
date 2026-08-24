module.exports = {
  apps: [
    {
      name: "dingtalk-gettime",
      cwd: __dirname,
      script: "main.py",
      // 使用 venv 内的 pythonw（无控制台子系统）启动，避免弹出黑框终端窗口。
      // 必须用 venv 的绝对路径：PM2 按守护进程 cwd 解析 interpreter，
      // 若用 "pythonw" 会命中全局 Python（未安装项目依赖），导致启动即崩溃重启。
      interpreter: "E:/GitHub/All_in_Ai/dingtalk_gettime/.venv/Scripts/pythonw.exe",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      // 进程至少要稳定运行 10 秒才视为健康，防止端口冲突等启动即崩溃时被误判为在线
      min_uptime: "10s",
      out_file: "./logs/pm2-out.log",
      error_file: "./logs/pm2-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
