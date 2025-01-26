import telebot
import datetime
import numpy as np
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import threading

class PeriodTracker:
    def __init__(self, bot_token: str):
        self.bot = telebot.TeleBot(bot_token)
        self.user_data = {}  # Stores user-specific cycle information

        self.register_commands()

    def register_commands(self):
        @self.bot.message_handler(commands=['log_period'])
        def log_period(message):
            user_id = message.from_user.id
            if user_id not in self.user_data:
                self.bot.reply_to(message, "Please start the bot first with /start")
                return

            # Mark that the user is logging a period start
            self.user_data[user_id]['logging_period'] = True
            self.bot.reply_to(message, "Period started. Enter the start date in YYYY-MM-DD format (or send 'today' for today).")
            self.bot.register_next_step_handler(message, self.process_period_log)

        @self.bot.message_handler(commands=['end_period'])
        def end_period(message):
            user_id = message.from_user.id
            if user_id not in self.user_data:
                self.bot.reply_to(message, "Please start the bot first with /start")
                return

            # Mark that the user has ended their period
            self.user_data[user_id]['period_active'] = False
            self.bot.reply_to(message, "Period ended. Tracking stopped.")

        @self.bot.message_handler(commands=['add_cycle_length'])
        def add_cycle_length(message):
            user_id = message.from_user.id
            self.user_data[user_id]['waiting_for_cycle_length'] = True  # Set the flag
            self.bot.reply_to(message, "Please enter your cycle length in days (e.g., 28).")
            self.bot.register_next_step_handler(message, self.process_cycle_length)

        @self.bot.message_handler(commands=['last_period'])
        def update_last_period(message):
            user_id = message.from_user.id
            self.user_data[user_id]['waiting_for_cycle_length'] = False  # Reset the flag
            self.bot.reply_to(message, "Please enter the start date of your last period in YYYY-MM-DD format (e.g., 2023-05-01).")
            self.bot.register_next_step_handler(message, self.process_last_period)

        @self.bot.message_handler(commands=['next_period'])
        def predict_next_period(message):
            user_id = message.from_user.id
            self.user_data[user_id]['waiting_for_cycle_length'] = False
            if user_id not in self.user_data or not self.user_data[user_id]['cycles']:
                self.bot.reply_to(message, "No cycle data available. Please add your cycle length first using /add_cycle_length")
                return

            next_period_date = self._predict_next_period(user_id)
            days_until_period = (next_period_date - datetime.date.today()).days
            self.bot.reply_to(message, f"Predicted next period: {next_period_date.strftime('%B %d, %Y')}\nDays until next period: {days_until_period}")

        # Register command handlers
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            user_id = message.from_user.id
            if user_id not in self.user_data:
                self.bot.reply_to(message, "Welcome! What is your name?")
                self.bot.register_next_step_handler(message, self.save_user_name)
            else:
                self.show_menu(message)

        @self.bot.message_handler(commands=['ovulation'])
        def predict_ovulation(message):
            user_id = message.from_user.id
            self.user_data[user_id]['waiting_for_cycle_length'] = False 
            if user_id not in self.user_data or not self.user_data[user_id]['cycles']:
                self.bot.reply_to(message, "No cycle data available. Please add your cycle length first using /add_cycle_length")
                return

            ovulation_date = self._predict_ovulation(user_id)
            days_until_ovulation = (ovulation_date - datetime.date.today()).days
            
            self.bot.reply_to(message, 
                f"Predicted ovulation date: {ovulation_date.strftime('%B %d, %Y')}\n"
                f"Days until ovulation: {days_until_ovulation}")
        
        @self.bot.message_handler(commands=['restart'])
        def restart_data(message):
            user_id = message.from_user.id
            self.user_data[user_id]['waiting_for_cycle_length'] = False 
            if user_id in self.user_data:
                self.user_data[user_id] = {
                    'name': self.user_data[user_id]['name'],
                    'cycles': []
                }
                self.bot.reply_to(message, "Your cycle data has been reset.")
            else:
                self.bot.reply_to(message, "You don't have any cycle data to reset.")
    
    def process_period_log(self, message):
        user_id = message.from_user.id
        
        # Determine the period start date
        if message.text.strip().lower() == "today":
            period_start = datetime.date.today()
        else:
            try:
                period_start = datetime.datetime.strptime(message.text, '%Y-%m-%d').date()
            except ValueError:
                self.bot.reply_to(message, "Invalid date format. Please use YYYY-MM-DD.")
                return

        # Calculate cycle length if previous period exists
        if 'last_period_start' in self.user_data[user_id]:
            cycle_length = (period_start - self.user_data[user_id]['last_period_start']).days
            
            if cycle_length > 0:
                self._update_cycle_data(user_id, cycle_length)

        # Update last period start and set period as active
        self.user_data[user_id]['last_period_start'] = period_start
        self.user_data[user_id]['period_active'] = True
        self.user_data[user_id]['logging_period'] = False

        self.bot.reply_to(message, f"Period logged for {period_start}.")
    
    def start_periodic_notifications(self):
        """Start background task for periodic notifications."""
        while True:
            # Check for upcoming periods and send notifications
            for user_id, data in self.user_data.items():
                try:
                    # Skip if no cycle data
                    if not data.get('cycles'):
                        continue

                    next_period = self._predict_next_period(user_id)
                    days_until_period = (next_period - datetime.date.today()).days
                    
                    # Send notification 5 days before period (changed from 3 to 5)
                    if days_until_period <= 5:
                        self.bot.send_message(user_id, 
                            f"🩸 Hey {data['name']}! Your period is expected in {days_until_period} days. "
                            "Be prepared and take care of yourself! 💕")
                    
                    # Supportive notifications only during active period
                    if data.get('period_active', False):
                        if days_until_period % 2 == 0:  # More frequent during period
                            self._send_supportive_notification(user_id)
                
                except Exception as e:
                    print(f"Error sending notification: {e}")
            
            # Wait for a day before checking again
            time.sleep(86400) 
    
    def process_last_period(self, message):
        try:
            last_period_start = datetime.datetime.strptime(message.text, '%Y-%m-%d').date()
            self._update_last_period(message.from_user.id, last_period_start)
            self.bot.reply_to(message, f"Last period start date updated to {last_period_start}.")
        except ValueError:
            if message.text.startswith('/'):
                self.bot.process_new_messages([message])
                return
            else:
                self.bot.reply_to(message, "Invalid input. Please provide a valid date in the format YYYY-MM-DD.")
    
    def process_cycle_length(self, message):
        user_id = message.from_user.id
        
        # Check if the message is a command
        if message.text.startswith('/'):
            self.bot.clear_step_handler_by_chat_id(user_id)
            self.user_data[user_id]['waiting_for_cycle_length'] = False
            # Manually process the command
            self.bot.process_new_messages([message])
            return

        if self.user_data[user_id].get('waiting_for_cycle_length', False):
            try:
                cycle_length = int(message.text)
                self._update_cycle_data(user_id, cycle_length)
                self.bot.reply_to(
                    message,
                    f"Cycle length of {cycle_length} days recorded. If you want to add another, just send the number or use another command."
                )
                self.bot.register_next_step_handler(message, self.process_cycle_length)
            except ValueError:
                if message.text.startswith('/'):
                    self.bot.process_new_messages([message])
                    return
                else:
                    
                    self.bot.reply_to(message, "Invalid input. Please provide a valid number for the cycle length.")

    def _update_cycle_data(self, user_id: int, cycle_length: int):
        """Update user's cycle data with new information."""
        if user_id not in self.user_data:
            self.user_data[user_id]['cycles'] = []
        
        # Add new cycle length
        self.user_data[user_id]['cycles'].append(cycle_length)

    def _update_last_period(self, user_id: int, last_period_start: datetime.date):
        if user_id not in self.user_data:
            self.user_data[user_id] = {
                'cycles': [],
                'last_period_start': last_period_start
            }
        else:
            self.user_data[user_id]['last_period_start'] = last_period_start

    def _predict_next_period(self, user_id: int) -> datetime.date:
        """Predict next period date based on historical cycle data."""
        cycles = self.user_data[user_id]['cycles']
        avg_cycle_length = round(np.mean(cycles))
        
        last_period_start = self.user_data[user_id]['last_period_start']
        return last_period_start + datetime.timedelta(days=avg_cycle_length)

    def _predict_ovulation(self, user_id: int) -> datetime.date:
        """Predict ovulation date (typically 14 days before next period)."""
        next_period = self._predict_next_period(user_id)
        return next_period - datetime.timedelta(days=14)

    def start_periodic_notifications(self):
        """Start background task for periodic notifications."""
        while True:
            # Check for upcoming periods and send notifications
            for user_id, data in self.user_data.items():
                try:
                    next_period = self._predict_next_period(user_id)
                    days_until_period = (next_period - datetime.date.today()).days
                    
                    # Send notification 3 days before period
                    if days_until_period == 3:
                        self.bot.send_message(user_id, 
                            "🩸 Hey Fatemeh! Your period is expected in 3 days. "
                            "Be prepared and take care of yourself! 💕")
                    
                    # Some random supportive notifications
                    if days_until_period % 7 == 0:  # Every week
                        self._send_supportive_notification(user_id)
                
                except Exception as e:
                    print(f"Error sending notification: {e}")
            
            # Wait for a day before checking again
            time.sleep(86400)  # 24 hours
    
    def save_user_name(self, message):
        user_id = message.from_user.id
        name = message.text
        self.user_data[user_id] = {'name': name, 'cycles': [], 'last_period_start': datetime.date.today()}
        self.show_menu(message)
    
    def show_menu(self, message):
            user_id = message.from_user.id
            name = self.user_data[user_id]['name']

            # Create the menu buttons
            menu_buttons = [
                KeyboardButton("/log_period"),
                KeyboardButton("/end_period"),
                KeyboardButton("/add_cycle_length"),
                KeyboardButton("/last_period"),
                KeyboardButton("/next_period"),
                KeyboardButton("/ovulation"),
                KeyboardButton("/restart")
            ]

            # Create the markup and send the menu
            menu_markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
            menu_markup.add(*menu_buttons)
            self.bot.send_message(
                chat_id=message.chat.id,
                text=f"Hello {name}! Here are the available commands:",
                reply_markup=menu_markup
            )

    def _send_supportive_notification(self, user_id: int):
        """Send a supportive notification to user."""
        name = self.user_data[user_id]['name']
        supportive_messages = [
            f"Hey {name}! Remember to be kind to yourself during your cycle. 💖",
            "Feeling a bit off? That's totally normal. You're strong and amazing! 💪",
            "Self-care is important, Fatemeh. Take some time for yourself today. 🌷",
            "Your body is doing incredible work. You're awesome! 🌈"
        ]
        
        import random
        message = random.choice(supportive_messages)
        self.bot.send_message(user_id, message)

    def run(self):
        """Start the bot and run it continuously."""
        
        # Start notification thread
        notification_thread = threading.Thread(target=self.start_periodic_notifications)
        notification_thread.daemon = True
        notification_thread.start()
        
        # Start bot polling
        self.bot.polling()

# Usage
if __name__ == '__main__':
    BOT_TOKEN = 'YOUR_BOT_TOKEN'
    tracker = PeriodTracker(BOT_TOKEN)
    tracker.run()