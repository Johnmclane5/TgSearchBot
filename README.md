# Telegram File Store Bot

This is a powerful and asynchronous Telegram bot designed for efficient file storage, retrieval, and sharing. It's built with Pyrogram and uses MongoDB for robust database management. The bot also includes a FastAPI backend to support advanced features like direct downloads and streaming to external players.

## Key Features

-   **Seamless File Storage**: Automatically index and store any file sent to a designated Telegram channel.
-   **Instant Search**: Quickly search for files by name across all indexed channels.
-   **Direct Download & Streaming**:
    -   Generate direct download links for any file.
    -   Stream video files directly in a web browser.
    -   Open video streams in external players like **VLC** and **MX Player** with a single tap.
-   **Content Protection**: Files sent to users are protected, preventing them from being forwarded.
-   **User Authorization**: Secure the bot with a token-based authorization system to control access.
-   **Concurrency Limiting**: Optimized for low-resource environments with a built-in limiter for concurrent streams.
-   **Docker Support**: Includes a `Dockerfile` for easy containerization and deployment.

## Project Structure

```
.
├── handlers/
│   ├── owner.py      # Handlers for bot owner commands
│   ├── user.py       # Handlers for general user commands
│   └── callbacks.py  # Handlers for inline button callbacks
├── .gitignore
├── Atlas.txt
├── Dockerfile
├── app.py            # Core Bot class initialization
├── bot.py            # Main entry point for the bot
├── cache.py
├── config.py         # Configuration loader (from .env)
├── db.py             # MongoDB database connection and setup
├── fast_api.py       # FastAPI server for streaming/downloading
├── query_helper.py
├── requirements.txt
├── tmdb.py
├── update.py
└── utility.py        # Helper functions and utilities
```

-   `bot.py`: The main script to run the bot.
-   `app.py`: Initializes the Pyrogram Client.
-   `handlers/`: Contains all the logic for handling messages, commands, and callbacks.
-   `db.py`: Manages the connection to the MongoDB database and defines collections.
-   `fast_api.py`: The FastAPI application that serves files for streaming and downloading.
-   `config.py`: Loads all environment variables from your `.env` file.
-   `utility.py`: A collection of helper functions used across the application.
-   `Dockerfile`: A pre-configured file to build a Docker image for the bot.

## Setup Instructions

### Prerequisites

-   Python 3.8 or higher
-   A running MongoDB instance (local or on a cloud service like MongoDB Atlas)
-   A Telegram account

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Install Dependencies

Install all the required Python packages using pip:

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

1.  Rename the sample configuration file from `config.env.sample` to `.env`:
    ```bash
    mv config.env.sample .env
    ```

2.  Open the `.env` file and fill in the required values:

    -   `API_ID`: Your Telegram API ID (get this from [my.telegram.org](https://my.telegram.org)).
    -   `API_HASH`: Your Telegram API Hash.
    -   `BOT_TOKEN`: The token for your Telegram bot (get this from [@BotFather](https://t.me/BotFather)).
    -   `DB_URI`: Your MongoDB connection string.
    -   `MY_DOMAIN`: The public domain or IP address where your bot's FastAPI server will be accessible (e.g., `https://mybot.example.com`). **This must be a valid and accessible URL.**

### 4. Run the Bot

Start the bot by running the `bot.py` script:

```bash
python3 bot.py
```

The bot should now be running, and the FastAPI server will be available at the domain you specified.

## Contributing

Contributions are welcome! If you have any improvements or features to add, please feel free to submit a pull request.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.