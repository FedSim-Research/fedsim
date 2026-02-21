module.exports = {
  apps: [
    {
      name: "backend",
      script: "./.venv/bin/python",
      args: "-m uvicorn backend.main:app --reload",
      cwd: ".",
    },
    {
      name: "frontend",
      script: "npm",
      args: "run start",
      cwd: "./frontend",
    },
    {
      name: "ray",
      script: "./start_ray.sh",
      cwd: "./frontend",
    },
    {
      name: "prometheus",
      script: "prometheus",
      args: "--config.file=prometheus.yml --web.listen-address=:9010",
      cwd: "./frontend",
    },
    {
      name: "loki",
      script: "loki",
      args: "--config.file=loki.yml",
      cwd: "./frontend",
    },
    {
      name: "grafana",
      script: "./start_grafana.sh",
      cwd: "./frontend",
    },
  ],
};
