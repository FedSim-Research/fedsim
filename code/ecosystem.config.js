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
    }
  ],
};
