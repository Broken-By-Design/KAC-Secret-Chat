# KAC Chat

KAC Chat is a real-time web-based chat application designed for engaging and interactive communication. It leverages modern web technologies to provide a seamless experience for users and administrators alike.

## Features

- Real-time Messaging: Fast and reliable communication using Flask-SocketIO.
- Integrated AI Bot: KAC-Bot, powered by Google Gemini, participates in conversations with a unique personality and access to Google Search.
- Multimedia Sharing: Support for uploading and viewing images within the chat.
- Video Lounge: A dedicated space for video calls using WebRTC, including screen sharing capabilities.
- Administrative Controls: A comprehensive admin panel to manage users, including features to kick, mute, or ban participants.
- Security: Secure login systems for both users and administrators.
- Persistence: Chat logs are stored and can be retrieved, ensuring continuity in conversations.

## Technology Stack

- Backend: Flask, Flask-SocketIO
- AI Integration: Google GenAI (Gemini)
- Database: MySQL for user management and ban lists
- Real-time Communication: Socket.IO, Eventlet
- Frontend: HTML5, CSS3, JavaScript (WebRTC for video)

## Installation

1. Clone the repository to your local machine.
2. Install the required Python packages:
```bash
pip install -r requirements.txt
```
3. Create a .env file in the root directory and populate it with the necessary environment variables.

## Configuration

The application requires several environment variables to function correctly. Ensure these are set in your .env file:

- SECRET_KEY: Used for session security.
- CHAT_SECRET_KEY: The password required for users to enter the chat.
- ADMIN_SECRET_KEY: The password required to access the admin panel.
- GEMINI_API_KEY: Your API key for Google Gemini.
- DB_HOST: Hostname for the MySQL database.
- DB_PORT: Port number for the MySQL database (default is 3306).
- DB_USER: Username for the database.
- DB_PASSWORD: Password for the database.
- DB_NAME: Name of the database.

## Running the Application

To start the server, execute the following command:
```bash
python main.py
```

The application will be accessible via your web browser, typically at http://localhost:5000 or the configured proxy address.

## License

This project is licensed under the GNU General Public License Version 3. See the LICENSE file for details.
