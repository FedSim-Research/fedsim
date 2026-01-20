# RP_FedSim

## Backend setup

From the project root:

```bash
python -m venv .venv
# If `python` is not available, use: python3 -m venv .venv
source .venv/bin/activate # Linux/macOS
# Windows PowerShell:
# .\\.venv\\Scripts\\Activate.ps1

cd code
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, and Swagger UI at
`http://127.0.0.1:8000/docs`.

## Frontend setup

```bash
cd code/frontend
npm install
npm run start
```

The frontend is available at `http://localhost:4200`.

## Flower simulation setup
Currently, the Flower simulation (explicitly ray) only supports Linux. To run simulations on a Windows machine, use WSL2 and follow this guide using the Linux commands.

Assumes the `.venv` is already created and activated (see Backend setup above).

The setup can be checked using the command `which pip` for Linux and `gcm pip` for PowerShell. Confirm that the path to pip corresponds to:
- Linux: `<path to project-root>/code/.venv/bin/pip`
- Powershell: `<path to project-root>/code/.venv/Scripts/pip`

For the next step, flower has to be installed by pip. By using the `-e` flag it is ensured that changes made to the custom flower implementation in this project are instantly reflected when using the `flwr` command.
```bash
cd ./code/framework/flower/framework/
pip install -e .
pip install -e ".[simulation]"
```

Beware, the download size of all necessary dependencies is roughly 8GB.
To confirm this step has succeeded, the following path checks can be performed:

Linux:
- `which flwr` should point to `<path to project-root>/code/.venv/bin/flwr`
- `which flower-simulation` should point to `<path to project-root>/code/.venv/bin/flower-simulation`

Powershell:
- `gcm flwr` should point to `<path to project-root>/code/.venv/Scripts/flwr`
- `gcm flower-simulation` should point to `<path to project-root>/code/.venv/Scripts/flower-simulation`

In order to be REALLY sure that the custom implementation of the flower framework is used, the following code can be temporarily injected into the startup file located at:

 `<path to project-root>/code/framework/flower/framework/py/flwr/__init__.py`

In order to work properly, the following code has to be inserted at the very top of the file. (even above all imports!)
 ```python
print("\n" + "="*53)
print(">>> SUCCESS: You are using your CUSTOM LOCAL FLWR <<<")
print("="*53 + "\n")
 ```

## Run a Flower simulation
Finally, to run a simulation and see the work of this code injection, use the following commands:

Starting from project root:
```bash
flwr run ./code/framework/impl/
```

An output file, called `final_model.pt` will be created, which unsurprisingly contains the final model after the simulation has ended and the model has been trained. This file is located wherever the above mentioned `flwr` run is started.
