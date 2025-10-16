# Telegram File Bot

This is a powerful Telegram bot for storing and retrieving files. It uses MongoDB as a database and includes a FastAPI component for potential web integrations.

## Features

- **File Storage:** Store any file from a Telegram chat directly into the bot's database.
- **File Search:** Search for files by name.
- **Asynchronous:** Built with `asyncio` and `pyrogram` for high performance.

## Project Structure

```
.
├── handlers/
│   ├── owner.py
│   ├── user.py
│   └── callbacks.py
├── tests/
│   └── test_helpers.py
├── .gitignore
├── Atlas.txt
├── Dockerfile
├── app.py
├── bot.py
├── cache.py
├── config.py
├── db.py
├── fast_api.py
├── query_helper.py
├── requirements.txt
├── tmdb.py
├── update.py
└── utility.py
```

- `bot.py`: The main entry point for the bot.
- `app.py`: Contains the core `Bot` class.
- `handlers/`: Contains the message handlers for different types of users and callbacks.
- `db.py`: Handles the connection to the MongoDB database.
- `fast_api.py`: The FastAPI application.
- `config.py`: Configuration file for API keys and other settings.
- `requirements.txt`: The list of Python dependencies.
- `Dockerfile`: For containerizing the application.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/your-repo-name.git
   cd your-repo-name
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up configuration:**
   - Rename `.env.example` to `.env`.
   - Edit the `.env` file and add your Telegram API ID, API hash, bot token, and MongoDB connection string.

4. **Run the bot:**
   ```bash
   python bot.py
   ```

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.