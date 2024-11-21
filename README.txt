# Food Deserts Visualization Project

DESCRIPTION

This project provides interactive visualizations of food desert data across different regions.
There are two tools that have been developed for this project:

- A website to compare grocery store locations with Social Vulnerability Index (SVI) data in the US. SVI data is collected by the Center of Disease Control and it is commonly used for understanding where disadvantaged populations live in the US. This website can be accessed through a URL in a web browser or by running locally on a localhost server. Instructions for both of these options are below.

- A local Jupyter notebook that demonstrates a distance-based mapping algorithm to display areas of potential food deserts locally. Street maps are visualized in this application based on their distance from a grocery store.

INSTALLATION

1. The Website (Option #1 - Using the Internet) - The easiest way to access the website is by pasting this URL into your web browser: food-desert-analysis.com. No installations are required to run this website on your computer. Please note that this site has been optimized for computer use. While phone use is possible, the visuals have been tailored to a computer experience.
   
2. The Website (Option #2 - Running the App Locally) - If you would prefer to run this website on your local machine, the first step is to change your working directory to the CODE folder included in this package after downloading.

(Optional) Once in the CODE folder, a Python virtual environment can be installed if you would like to separate the dependencies for this project from your local machine. For an easier to read version of this process, please refer to the following source to set up a virtual environment in Python: https://www.freecodecamp.org/news/how-to-setup-virtual-environments-in-python/ 
Install Python's virtual environment package if you do not have it using this terminal code: 'python -m venv <custom_name_for_your_virtual_environment>'.
Next, create a virtual environment with this command: 'python -m venv <name_of_virtual-environment_name>'. The name of your environment is your choice.
Activate the environment with 'source <name_of_virtual-environment_name>/bin/activate'. You are now ready to install dependencies in a virtual environment separate from the rest of your machine.

Install all dependencies required in requirements.txt by running "pip install -r requirements.txt". If you followed the virtual environment steps above, the above dependencies will be installed outside of your regular Python system.

Run the app by entering the command "python app.py"

If the run was successful, the app will display a message saying "Running on http://127.0.0.1:8050". Copy/paste this URL into your web browser or enter "localhost:8050" in your web browser to access the app.

Note: in the commands above "python" and "pip" were used. These may need to be replaced with "python3" and "pip3" Depending on your Python set-up. Note that our app is untested on Python versions earlier than 3.10, so updates may be required if the application is not running.

3. The Jupyter Notebook - Once the CODE folder is downloaded from the .zip file, open the CODE folder in your preferred Jupyter Notebook-capable Integrated Development Environment (IDE). This code was tested in Microsoft's Visual Studio Code IDE using the Jupyter Notebook extension. Open the file that is.ipynb type. Code cells can be run individually through the on-screen prompts or all-at-once by selecting 'Run All'.

Prerequisites - Tested using Python 3.10. Installation instructions for other dependencies are mentioned above.

EXECUTION

1. The Website (Option #1 - Using the Internet) - Go to food-desert-analysis.com in your web browser.
2. The Website (Option #2 - Running the App Locally)  - Run the command 'python app.py' in your terminal after navigating to the downloaded CODE file, or run App.py through an IDE.
3. The Jupyter Notebook - Open the CODE file in your IDE and run the .ipynb file in a compatible IDE.

Thank you. If you have questions, please feel free to reach out to Joshua Farina, Morgan Johnson, Christopher McCormick, or Stephen Schanes. 

