# Scrapeseek

## Introduction

I passionately developed Scrapeseek, inspired by the need to bridge the gap between Deepseek web chat and agent-based APIs, ensuring compatibility with OpenAI's architecture. My thought process revolved around creating an efficient Python-based solution to simplify and enhance the conversion process while maintaining a user-centric design approach.

## Features

- **Deepseek Web Chat Conversion:** Converts Deepseek web chat interfaces into agentic APIs.
- **OpenAI Compatibility:** Fully compatible with OpenAI, ensuring seamless integration.
- **Python-Based Implementation:** Entirely developed in Python, emphasizing simplicity and performance.

## Table of Contents

1. [Introduction](#introduction)
2. [Features](#features)
3. [Getting Started](#getting-started)
4. [Installation](#installation)
5. [Usage](#usage)
6. [Contributing](#contributing)
7. [License](#license)

## Getting Started

This project aims to make it easier for users to transform Deepseek web chat into functional APIs. To begin, you need to have Python installed on your system and follow the steps under Installation and Usage.

## Installation

1. **Clone this repository**  
   ```bash
   git clone https://github.com/kiruthik2006/scrapeseek.git
   ```

2. **Navigate to the project directory**  
   ```bash
   cd scrapeseek
   ```

3. **Install dependencies**  
   Ensure you have `pip` installed and run the following command:  
   ```bash
   pip install -r requirements.txt
   ```
   Then create a .env file in the main folder like this:
   ```bash
   DS_EMAIL=<your>@gmail.com
   DS_PASSWORD=<Password>
   ```

## Usage

1. Run the script to convert Deepseek web chat into an agentic API:  
   ```bash
   uvicorn api_v5:app --host 0.0.0.0 --port 8000 --reload

   ```

2. Follow the prompts provided by the script to integrate and test with OpenAI-compatible APIs.

3. Refer to the comments in the Python script for additional functionality and customization options.

## Contributing

Contributions to Scrapeseek are welcome and encouraged! If you'd like to contribute:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature-branch`).
3. Commit your changes (`git commit -m 'Add new feature'`).
4. Push to the branch (`git push origin feature-branch`).
5. Submit a pull request.

Please follow the existing style guide and ensure the code is well-documented.

## License

This project is licensed under the MIT License
