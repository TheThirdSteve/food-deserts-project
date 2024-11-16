# food-deserts-project
repo for class project

# 1. Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install requirements from requirements.txt

pip install -r requirements.txt

# 3. Run with Gunicorn
gunicorn app:server --bind 0.0.0.0:8000

# 4. Open from localhost

http://127.0.0.1:8700