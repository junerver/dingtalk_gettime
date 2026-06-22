module.exports = {
  apps: [
    {
      name: "dingtalk-gettime",
      cwd: __dirname,
      script: "main.py",
      interpreter: "python",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 10,
      out_file: "./logs/pm2-out.log",
      error_file: "./logs/pm2-error.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
