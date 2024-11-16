# Food Deserts Visualization Project

This project provides interactive visualizations of food desert data across different regions.

## Prerequisites
- Tested using Python 3.10


## Installation & Setup

1. **Create and activate a virtual environment**

   Create a new virtual environment:
   ```bash
   # For most systems (assuming python 3 is installed as python)
   python -m venv venv
   
   # For Linux systems 
   python3 -m venv venv
   ```

   Activate the virtual environment:
   ```bash
   # For Unix/Linux/MacOS
   source venv/bin/activate
   
   # For Windows
   venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   gunicorn app:server --bind 0.0.0.0:8000
   ```

4. **Access the application**
   
   Open your web browser and navigate to:
   http://127.0.0.1:8000

## Troubleshooting

- If port 8000 is already in use, you can specify a different port:
  ```bash
  gunicorn app:server --bind 0.0.0.0:8050
  ```

- If you see "command not found: gunicorn", ensure you've activated your virtual environment

