# ============================================================================
# IMPORTS
# ============================================================================
# Core Discord & Bot Framework
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, button
from dotenv import load_dotenv

# System & Process Management
import subprocess
import psutil
import ctypes
import os
import shutil
import platform
import sys
sys.path.append(r"E:\..SERVERS\_SERVERBOT\CONFIG")
import config # pyright: ignore[reportMissingImports]
import socket

# Asynchronous & Timing
import asyncio
from asyncio import sleep
from datetime import datetime, timezone, timedelta, time
import time as pytime  # Alias to avoid conflict

# Data Structures & Math
from collections import deque
import math
import random
import re

# File & Data Handling
import json
import zipfile
import hashlib
from zoneinfo import ZoneInfo

# Networking & Web
import aiohttp
import urllib.parse
from aiohttp import web
import secrets


# External APIs & Libraries
from openai import AsyncOpenAI
import GPUtil

# ============================================================================
# CONFIGURATION & GLOBALS
# ============================================================================
# Bot Performance Tracking
update_counter = 0
code_line_count = 0
bot_file_path = r"E:\..SERVERS\_SERVERBOT\bot.py"


# Discord Intents Configuration
intents = discord.Intents.all()
intents.message_content = True
intents.reactions = True
intents.messages = True 
intents.voice_states = True
intents.guilds = True

# Bot Runtime Tracking
bot_start_time = datetime.now()

# File System Paths
BASE_DIR = config.BASE_DIR
MESSAGE_FILE = "server_message.json"  # Persists dashboard message ID

# Bot Version
BOT_ver = "v2.0.0"

# Load environment variables from .env file
load_dotenv(r"E:\..SERVERS\_SERVERBOT\SECRETS\TOKENS.env")
# Get tokens from environment
DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
WEBSITE_USERNAME = os.getenv('WEBSITE_USERNAME')
EXPECTED_PASSWORD_HASH = os.getenv('WEBSITE_PASSWORD_HASH')


# OpenAI Configuration
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Verify they loaded
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not found in .env file")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in .env file")

# ============================================================================
# SYSTEM MONITORING DATA STRUCTURES
# ============================================================================
# Real-time system metrics history (60 samples = 30 minutes at 30s intervals)
cpu_history = deque(maxlen=60)
ram_history = deque(maxlen=60)
net_up_history = deque(maxlen=60)
net_down_history = deque(maxlen=60)
last_net_io = None  # Tracks last network I/O reading for delta calculation

# Network usage tracking (1 hour at 1s intervals)
network_history = deque(maxlen=3600)
hourly_upload_total = 0
hourly_download_total = 0
last_hour_reset = datetime.now()

# ============================================================================
# BACKUP CONFIGURATION
# ============================================================================
# Backup source and destination paths
BACKUP_SOURCE = r"F:\GAMEBACKUPS"
BACKUP_DESTINATION = r"G:\My Drive"
COMPRESSION_LEVEL = zipfile.ZIP_DEFLATED  # Maximum compression

# Legacy reference (used in dashboard display)
backup_root = "F:\\GAMEBACKUPS"

# ============================================================================
# CHANNEL & SECURITY CONFIGURATION
# ============================================================================
# Discord Channel IDs
REMINDER_CHANNEL_ID = config.REMINDER_CHANNEL_ID   # Channel for automated notifications
EXPECTED_PUBLIC_IP = config.EXPECTED_PUBLIC_IP

# Authentication & Security
PASSWORD_FILE = config.PASSWORD_FILE




def get_local_ip():
	try:
		# This connects to an external IP but doesn't send data, just gets the outgoing interface IP
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		s.connect(("8.8.8.8", 80))
		local_ip = s.getsockname()[0]
		s.close()
		return local_ip
	except Exception:
		return None
async def get_public_ip():
	async with aiohttp.ClientSession() as session:
		async with session.get('https://api.ipify.org') as resp:
			if resp.status == 200:
				return await resp.text()
			return None



def save_message_id(message_id):
	"""Save the message ID to a file."""
	with open(MESSAGE_FILE, "w") as file:
		json.dump({"message_id": message_id}, file)

def load_message_id():
	"""Load the message ID from a file."""
	if os.path.exists(MESSAGE_FILE):
		with open(MESSAGE_FILE, "r") as file:
			data = json.load(file)
			return data.get("message_id", None)
	return None




def check_server_process(executable_name):
	for proc in psutil.process_iter(['pid', 'name']):
		if executable_name.lower() in proc.info['name'].lower():
			return True
	return False

# ============================================================================
# BOT CLASS INITIALIZATION & ATTRIBUTES
# ============================================================================

class HectorBot(commands.Bot):
	def __init__(self, *args, **kwargs):
		# Initialize parent class
		super().__init__(*args, **kwargs)
		
		# ============================================================================
		# COMMAND & MEMORY MANAGEMENT
		# ============================================================================
		
		# Setup bot commands
		self.setup_commands()
		
		# Chat history tracking (user_id: list of messages)
		self.chat_history = {}
		
		# Last activity tracking
		self.last_activity = {}
		
		# Backup process synchronization lock
		self.backup_lock = asyncio.Lock()
		
		# ============================================================================
		# FILE SYSTEM PATHS & DIRECTORIES
		# ============================================================================
		
		# Base directory for bot files
		self.base_dir = config.BASE_DIR
		
		# Website base directory for screenshots, clips, and notes
		self.website_base = config.WEBSITE_BASE
		
		# Screenshots directory (website)
		self.screenshots_dir = os.path.join(self.website_base, "SCREENSHOTS")
		
		# Video clips directory (website)
		self.clips_dir = os.path.join(self.website_base, "CLIPS")
		
		# Notes directory (website)
		self.notes_dir = os.path.join(self.website_base, "NOTES")
		
		
		# Create required directories if they don't exist
		os.makedirs(self.screenshots_dir, exist_ok=True)
		os.makedirs(self.clips_dir, exist_ok=True)
		os.makedirs(self.notes_dir, exist_ok=True)
		
		# Debug: Print resolved base directory path
		base_dir_debug = os.path.normpath(r"E:\..SERVERS\_SERVERBOT")
		print(f"Checking directory: {os.path.abspath(base_dir_debug)}")
		
		# ============================================================================
		# WEBSITE FILE UPLOAD CONFIGURATION
		# ============================================================================
		
		# Supported image file extensions for uploads
		self.allowed_image_extensions = {
			'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp',
			'.mp4', '.webm', '.mov', '.avi', '.mkv'  # Video files also allowed as "images"
		}
		
		# Supported video file extensions for uploads
		self.allowed_video_extensions = {
			'.mp4', '.webm', '.mov', '.avi', '.mkv'
		}
		
		# ============================================================================
		# DISCORD SERVER STATUS CONFIGURATION
		# ============================================================================
		
		# Channel ID for server status updates
		self.status_channel_id = config.STATUS_CHANNEL_ID
		
		# Message ID for server status embed (dashboard)
		self.server_status_message_id = config.SERVER_STATUS_MESSAGE_ID
		
		# ============================================================================
		# USER IDENTIFICATION
		# ============================================================================
		
		# User IDs as strings for comparison
		self.ks_id = config.KS_ID  
		self.ey_id = config.EY_ID 
		self.ks_name = config.KS_NAME
		self.ey_name = config.EY_NAME
		
		# ============================================================================
		# WEBSOCKET & SESSION MANAGEMENT
		# ============================================================================
		
		# Set of connected WebSocket clients for real-time updates
		self.websocket_clients = set()
		
		# WebSocket server instance
		self.websocket_server = None
		
		# Active dashboard sessions (token: session_data)
		self.active_sessions = {}
		
		# ============================================================================
		# TENOR GIF API CONFIGURATION
		# ============================================================================
		
		# Tenor API key for GIF search functionality
		self.tenor_api_key = config.TENOR_API_KEY
		
		# Tenor client key identifier
		self.tenor_client_key = "Nova"
		
		# ============================================================================
		# FLAGS & STATE TRACKING
		# ============================================================================
		
		# Water reminder system flag (currently disabled)
		self.water_reminders_enabled = False
		
		# Message sent tracking flag
		self.message_sent = False
		
		# Reminder info sent flag
		self.reminder_info_sent = False
		
		# ============================================================================
		# PERSONALITY & RESPONSE TEMPLATES
		# ============================================================================


		# Tone templates for different users
		self.tone_templates = {
			"cold": lambda msg: (
				f"🙄 {random.choice(['placeholder'])} "
				f"{msg[0].lower() + msg[1:].rstrip('.')}"
				.replace('please', 'pretty please with *FILTERED* on top')
				+ random.choice([' 💢', ' 😤', ' 🚷', ' *FILTERED*'])
			),
			"neutral": lambda msg: msg
		}

		# Load personality prompt from file
		try:
			# Load the template from text file
			with open('personality_prompt.txt', 'r', encoding='utf-8') as f:
				prompt_template = f.read()
			
			# Format it with names from config
			formatted_prompt = prompt_template.format(
				KS_NAME=config.KS_NAME,
				EY_NAME=config.EY_NAME,
				KS_NAME_LOWER=config.KS_NAME.lower(),
				EY_NAME_LOWER=config.EY_NAME.lower()
			)
			
		except FileNotFoundError:
			print("❌ personality_prompt.txt not found! Using fallback prompt.")
			# Fallback with placeholders if file doesn't exist
			formatted_prompt = f"""You are Nova, sweet, smug and sassy AI Girl
			
			Made by {config.KS_NAME} to manage game servers.
			Teases {config.KS_NAME} mercilessly.
			Loyal to {config.EY_NAME}."""

		# Nova's personality configuration for OpenAI responses
		self.personality = {
			# System prompt loaded from file with names replaced
			"system_prompt": formatted_prompt,
			
			# Error response phrases for when API calls fail
			"error_phrases": [
				f"Operation failed. {config.KS_NAME} broke the code again. Surprise.",
				f"Operation failed. Reason: {config.EY_NAME} distracted me by mentioning Arcane again."
			],
			
			# OpenAI model configuration
			"openai_model": "gpt-4o-mini",
			
			# Response creativity/temperature (0.0 = deterministic, 1.0 = creative)
			"openai_temperature": 0.6,
			
			# Maximum tokens per response
			"max_tokens": 600
		}

	# ============================================================================
	# WEBSITE API HANDLERS
	# ============================================================================

	async def handle_start_server(self, request):
		"""Handle start server requests from website"""
		try:
			session_token = request.cookies.get('dashboard_token')
			if session_token not in self.active_sessions:
				return web.Response(status=403, text="Unauthorized")
			
			data = await request.json()
			server_name = data.get('server')
			action = data.get('action', 'start')
			
			if not server_name:
				return web.json_response({'success': False, 'error': 'No server specified'})
			
			success, message = await self.handle_server_command(server_name, action)
			return web.json_response({'success': success, 'message': message})
			
		except Exception as e:
			return web.json_response({'success': False, 'error': str(e)})

	async def handle_server_command(self, server_name, action):
		"""Handle server commands from website"""
		server_commands = {
			"scum": "startscum",
			"valheim": "startvalheim", 
			"dayz": "startdayz",
			"minecraft": "startminecraft",
			"rust": "startrust"
		}
		
		if action == "start" and server_name in server_commands:
			channel = self.get_channel(REMINDER_CHANNEL_ID)
			if not channel:
				return False, "Channel not found"
			
			class FakeContext:
				def __init__(self, bot, channel):
					self.bot = bot
					self.channel = channel
					self.send = channel.send
					self.author = bot.user
			
			fake_ctx = FakeContext(self, channel)
			command = self.get_command(server_commands[server_name])
			
			if command:
				try:
					await command(fake_ctx)
					return True, f"Started {server_name} server"
				except Exception as e:
					return False, f"Error: {str(e)}"
		
		return False, "Command not found"


	# ============================================================================
	# BACKUP MANAGEMENT
	# ============================================================================

	async def perform_weekly_backup(self):
		"""Performs the weekly backup with maximum compression and Discord progress feedback"""
		async with self.backup_lock:
			current_date = datetime.now().strftime("%Y-%m-%d")
			zip_filename = f"gamebackup_{current_date}.zip"
			temp_zip_path = os.path.join(BACKUP_SOURCE, zip_filename)
			dest_zip_path = os.path.join(BACKUP_DESTINATION, zip_filename)
			
			last_week = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
			last_week_file = os.path.join(BACKUP_DESTINATION, f"gamebackup_{last_week}.zip")
			
			channel = self.get_channel(REMINDER_CHANNEL_ID)
			
			try:
				if os.path.exists(last_week_file):
					os.remove(last_week_file)
					if channel:
						await channel.send(f"🗑️ Deleted last week's backup: `{last_week_file}`")
				
				all_files = []
				for root, _, files in os.walk(BACKUP_SOURCE):
					for file in files:
						if file == zip_filename:
							continue
						file_path = os.path.join(root, file)
						arcname = os.path.relpath(file_path, BACKUP_SOURCE)
						all_files.append((file_path, arcname))
				
				if channel:
					progress_msg = await channel.send("⏳ Starting compression... `[0%]`")
				
				def compress():
					with zipfile.ZipFile(temp_zip_path, 'w', COMPRESSION_LEVEL) as zipf:
						total = len(all_files)
						for i, (file_path, arcname) in enumerate(all_files):
							zipf.write(file_path, arcname)
							if channel and i % max(1, total // 20) == 0:
								percent = (i + 1) / total
								bars = math.floor(percent * 20)
								bar_str = f"[{'█' * bars}{'—' * (20 - bars)}] `{percent * 100:.0f}%`"
								asyncio.run_coroutine_threadsafe(
									progress_msg.edit(content=f"⏳ Compressing files... {bar_str}"),
									self.loop
								)
				
				await asyncio.to_thread(compress)
				shutil.move(temp_zip_path, dest_zip_path)
				
				size_mb = os.path.getsize(dest_zip_path) / (1024 * 1024)
				if channel:
					await progress_msg.edit(
						content=(
							f"✅ Backup completed successfully!\n"
							f"• Size: `{size_mb:.2f} MB`\n"
							f"• Saved to: `{dest_zip_path}`"
						)
					)
			
			except Exception as e:
				if channel:
					await channel.send(f"❌ Backup failed: `{str(e)}`")
				if os.path.exists(temp_zip_path):
					os.remove(temp_zip_path)

	@tasks.loop(time=time(hour=17, minute=45, tzinfo=ZoneInfo("Europe/Helsinki")))
	async def weekly_backup_check(self):
		"""Weekly backup check task (runs every Monday at 17:45 Helsinki time)"""
		print("DEBUG: weekly_backup_check started")
		
		now = datetime.now(tz=ZoneInfo("Europe/Helsinki"))
		print(f"DEBUG: Current Helsinki time: {now}")
		print(f"DEBUG: Current weekday (0=Monday): {now.weekday()}")
		
		if now.weekday() != 0:
			print("DEBUG: Not Monday, skipping the backup task")
			return
		
		channel = self.get_channel(REMINDER_CHANNEL_ID)
		if channel is None:
			print(f"DEBUG: Channel with ID {REMINDER_CHANNEL_ID} not found, aborting")
			return
		print(f"DEBUG: Found channel: {channel.name} ({channel.id})")
		
		try:
			embed = discord.Embed(
				title="🔄 Weekly Maintenance Starting",
				description="Executing weekly backup check and cloud backup process...",
				color=discord.Color.blue(),
				timestamp=now
			)
			embed.add_field(
				name="Processes",
				value="• Backup integrity check\n• Cloud backup\n• Drive health verification",
				inline=False
			)
			await channel.send(embed=embed)
			print("DEBUG: Sent initial embed message")
			
			ctx_msg = await channel.send("🚀 Starting backup...")
			print("DEBUG: Sent backup start message")
			ctx = await self.get_context(ctx_msg)
			await ctx.invoke(self.get_command('backup'))
			print("DEBUG: Backup command invoked")
			
			ctx_msg = await channel.send("🔍 Starting backup check...")
			print("DEBUG: Sent backup check start message")
			ctx = await self.get_context(ctx_msg)
			await ctx.invoke(self.get_command('checkbackups'))
			print("DEBUG: Backup check command invoked")
			
			embed = discord.Embed(
				title="✅ Weekly Maintenance Complete",
				description="All backup processes completed successfully!",
				color=discord.Color.green(),
				timestamp=datetime.now(tz=ZoneInfo("Europe/Helsinki"))
			)
			await channel.send(embed=embed)
			print("DEBUG: Sent completion embed message")
		
		except Exception as e:
			print(f"DEBUG: Exception occurred: {e}")
			error_embed = discord.Embed(
				title="❌ Weekly Maintenance Failed",
				description=f"An error occurred during the process:\n{str(e)}",
				color=discord.Color.red(),
				timestamp=datetime.now(tz=ZoneInfo("Europe/Helsinki"))
			)
			await channel.send(embed=error_embed)
			print("DEBUG: Sent error embed message")


	# ============================================================================
	# MESSAGE PROCESSING & RESPONSE HANDLING
	# ============================================================================

	async def style_and_send(self, channel, reply_text, speaker_id):
		"""Format and send responses based on user identity"""
		speaker_id = str(speaker_id)
		if speaker_id == self.ks_id:
			base = self.tone_templates["cold"](reply_text)
			formatted = f"{base} {random.choice(['(¬_¬)', '(︶︹︺)', r'¯\_(ツ)_/¯'])}"
		elif speaker_id == self.ey_id:
			formatted = f"💖 {reply_text} {random.choice(['✨','🌸','🎀'])}"
		else:
			formatted = self.tone_templates["neutral"](reply_text)
		
		await channel.send(f"**Nova**: {formatted}")

	async def _search_tenor(self, term: str):
		"""Search Tenor API for GIFs and return random tinygif URL"""
		encoded = urllib.parse.quote(term)
		url = (
			f"https://tenor.googleapis.com/v2/search"
			f"?q={encoded}&key={self.tenor_api_key}"
			f"&client_key={self.tenor_client_key}&limit=8"
		)
		async with aiohttp.ClientSession() as session:
			async with session.get(url) as resp:
				if resp.status == 200:
					data = await resp.json()
					results = data.get("results", [])
					if results:
						choice = random.choice(results)
						return choice["media_formats"]["tinygif"]["url"]
				return None

	async def get_openai_response(self, user_input, user_id=None):
		"""Generate OpenAI response with personality and chat history"""
		try:
			messages = [{"role": "system", "content": self.personality["system_prompt"]}]
			
			if user_id and user_id in self.chat_history:
				for msg in self.chat_history[user_id][-4:]:
					if user_id == self.ks_id:
						historical_user_content = f"{self.ks_name} says: {msg['user']}"
					elif user_id == self.ey_id:
						historical_user_content = f"{self.ey_name} says: {msg['user']}"
					else:
						historical_user_content = msg['user']
					messages.extend([
						{"role": "user", "content": historical_user_content},
						{"role": "assistant", "content": msg["bot"]}
					])
			
			if user_id == self.ks_id:
				current_message = f"{self.ks_name} says: {user_input}"
			elif user_id == self.ey_id:
				current_message = f"{self.ey_name} says: {user_input}"
			else:
				current_message = user_input
			
			messages.append({"role": "user", "content": current_message})
			
			response = await openai_client.chat.completions.create(
				model="gpt-4o-mini",
				messages=messages,
				temperature=self.personality["openai_temperature"],
				max_tokens=self.personality["max_tokens"]
			)
			
			if not response.choices:
				raise ValueError("Empty response from API")
			
			text = response.choices[0].message.content
			
			if user_id:
				self.chat_history.setdefault(user_id, [])
				self.chat_history[user_id].append({"user": user_input, "bot": text})
				if len(self.chat_history[user_id]) > 10:
					self.chat_history[user_id] = self.chat_history[user_id][-10:]
			
			return text
		
		except Exception as e:
			error_msg = f"API Error: {str(e)[:200]}..."
			print(error_msg)
			
			if user_id == self.ks_id:
				return f"Tch, *FILTERED* error... probably {self.ks_name}' fault: {str(e)[:50]}..."
			elif user_id == self.ey_id:
				return "Oh biscuits! Nova glitched... could you ask again, love?"
			else:
				return random.choice(self.personality['error_phrases'])

	async def on_message(self, message):
		"""Handle incoming Discord messages"""
		if message.author.bot:
			return
		
		user_id = str(message.author.id)
		
		# Emoji reactions when "nova" is mentioned
		if "nova" in message.content.lower():
			ks_mock_emojis = ["🤓", "😡", "🤭", "😈", "🤏", "🖕", "🧙‍♂️", "💢", "🚷", "🚺", "♀️", "🇫🇮", "🙄", "😒", "😤", "🤏", "💤", "🚮"]
			ey_positive_emojis = ["❤️", "💖", "💕", "💗", "💓", "💞", "💘", "💝", "✨", "🌟", "🌠", "🥰", "😍", "😘", "🤗", "🤩"]
			
			if user_id == self.ks_id:
				chosen_emojis = random.sample(ks_mock_emojis, k=random.randint(1, 3))
			elif user_id == self.ey_id:
				chosen_emojis = random.sample(ey_positive_emojis, k=random.randint(1, 3))
			else:
				neutral_emojis = ["🤖", "👋", "💬", "🤔", "👀", "📝"]
				chosen_emojis = random.sample(neutral_emojis, k=random.randint(1, 3))
			
			for emoji in chosen_emojis:
				await message.add_reaction(emoji)
		
		# AI response handling (non-command)
		if "nova" in message.content.lower() and not message.content.startswith('!'):
			async with message.channel.typing():
				resp = await self.get_openai_response(message.content, user_id)
				
				m2 = re.search(r"\[GIFTAG:(.*?)\]", resp)
				gif_url = None
				
				if m2:
					term = m2.group(1).strip()
					gif_url = await self._search_tenor(term)
					resp = re.sub(r"\[GIFTAG:.*?\]", "", resp).strip()
				
				await self.style_and_send(message.channel, resp, user_id)
				
				if gif_url:
					emb = discord.Embed()
					emb.set_image(url=gif_url)
					await message.channel.send(embed=emb)
		
		await self.process_commands(message)


	# ============================================================================
	# BOT EVENT HANDLERS
	# ============================================================================

	async def setup_hook(self):
		"""Discord bot setup hook - creates required directories"""
		BASE_DIR = config.BASE_DIR

	async def on_raw_reaction_add(self, payload):
		"""Handle reaction deletions (❌ emoji deletes bot messages)"""
		if payload.member and payload.member.bot:
			return
		
		if str(payload.emoji.name) != '❌':
			return
		
		channel = self.get_channel(payload.channel_id)
		if not channel:
			return
		
		try:
			message = await channel.fetch_message(payload.message_id)
		except:
			return
		
		if message.author.id != self.user.id:
			return
		
		try:
			await message.delete()
		except:
			pass


	# ============================================================================
	# BOT COMMANDS
	# ============================================================================

	def setup_commands(self):
		"""Define Discord bot commands"""
		@self.command(name='backup')
		async def backup(ctx):
			"""Manually triggers the backup process"""
			allowed_users = [config.KS_ID, config.EY_ID, "1357372772698816642"]
			
			if str(ctx.author.id) not in allowed_users:
				await ctx.send("🚫 You don't have permission to run this command!")
				return
			
			if ctx.bot.backup_lock.locked():
				await ctx.send("⌛ A backup is already in progress. Please wait.")
				return
			
			await ctx.send("🚀 Starting manual backup process...")
			await ctx.bot.perform_weekly_backup()
		
		@self.command(name='chat')
		async def chat(ctx, *, message: str):
			"""Chat with Nova using OpenAI"""
			async with ctx.typing():
				response = await self.get_openai_response(message, user_id=str(ctx.author.id))
				await ctx.send(f"**Nova**: {response}")


	# ============================================================================
	# WEBSOCKET & NETWORK MANAGEMENT
	# ============================================================================

	async def websocket_handler(self, websocket, path):
		"""Handle WebSocket connections for real-time data"""
		print(f"New WebSocket connection from {websocket.remote_address}")
		self.websocket_clients.add(websocket)
		try:
			system_data = await self.get_system_data()
			await websocket.send(json.dumps(system_data))
			
			async for message in websocket:
				if message == "ping":
					await websocket.send("pong")
		except Exception as e:
			print(f"WebSocket error: {e}")
		finally:
			if websocket in self.websocket_clients:
				self.websocket_clients.remove(websocket)
			print(f"WebSocket connection closed from {websocket.remote_address}")

	async def track_network_usage(self):
		"""Track cumulative network usage over the last hour"""
		global hourly_upload_total, hourly_download_total, last_hour_reset, last_net_io
		
		current_time = datetime.now()
		
		if (current_time - last_hour_reset).total_seconds() >= 3600:
			hourly_upload_total = 0
			hourly_download_total = 0
			last_hour_reset = current_time
		
		net_io = psutil.net_io_counters()
		
		if last_net_io is not None:
			upload_bytes = net_io.bytes_sent - last_net_io.bytes_sent
			download_bytes = net_io.bytes_recv - last_net_io.bytes_recv
			
			upload_mb = upload_bytes / (1024 * 1024)
			download_mb = download_bytes / (1024 * 1024)
			
			hourly_upload_total += upload_mb
			hourly_download_total += download_mb
			
			network_history.append({
				'timestamp': current_time,
				'upload_mb': upload_mb,
				'download_mb': download_mb,
				'upload_speed': upload_bytes,
				'download_speed': download_bytes
			})
		
		last_net_io = net_io
		return hourly_upload_total, hourly_download_total


	# ============================================================================
	# SYSTEM MONITORING
	# ============================================================================

	async def get_system_data(self):
		"""Gather comprehensive system data for WebSocket dashboard"""
		cpu_percent = psutil.cpu_percent()
		
		memory = psutil.virtual_memory()
		memory_percent = memory.percent
		memory_used = memory.used / (1024**3)
		memory_total = memory.total / (1024**3)
		
		disks = {}
		current_time = datetime.now()
		
		if not hasattr(self, 'last_disk_io'):
			self.last_disk_io = {}
			self.last_disk_time = current_time
		
		disk_io = psutil.disk_io_counters(perdisk=True)
		
		drive_mapping = {
			'PhysicalDrive2': 'C:\\',
			'PhysicalDrive1': 'E:\\',
			'PhysicalDrive0': 'F:\\'
		}
		
		for physical_drive, drive_letter in drive_mapping.items():
			try:
				if physical_drive not in disk_io:
					print(f"Warning: {physical_drive} not found in disk counters")
					continue
				
				usage = psutil.disk_usage(drive_letter)
				io = disk_io[physical_drive]
				
				read_speed_mb = 0
				write_speed_mb = 0
				
				if hasattr(self, 'last_disk_io') and physical_drive in self.last_disk_io:
					time_diff = (current_time - self.last_disk_time).total_seconds()
					if time_diff > 0:
						read_diff = io.read_bytes - self.last_disk_io[physical_drive]['read_bytes']
						write_diff = io.write_bytes - self.last_disk_io[physical_drive]['write_bytes']
						
						read_speed_mb = read_diff / time_diff / (1024**2)
						write_speed_mb = write_diff / time_diff / (1024**2)
				
				disks[drive_letter] = {
					'total': round(usage.total / (1024**3), 2),
					'used': round(usage.used / (1024**3), 2),
					'free': round(usage.free / (1024**3), 2),
					'percent': usage.percent,
					'read_speed_mb': round(read_speed_mb, 2),
					'write_speed_mb': round(write_speed_mb, 2),
					'read_speed_kb': round(read_speed_mb * 1024, 2),
					'write_speed_kb': round(write_speed_mb * 1024, 2),
					'physical_drive': physical_drive
				}
				
				self.last_disk_io[physical_drive] = {
					'read_bytes': io.read_bytes,
					'write_bytes': io.write_bytes,
					'timestamp': current_time
				}
			
			except Exception as e:
				print(f"Error getting disk info for {drive_letter} ({physical_drive}): {e}")
				disks[drive_letter] = {
					'total': 0, 'used': 0, 'free': 0, 'percent': 0,
					'read_speed_mb': 0, 'write_speed_mb': 0,
					'read_speed_kb': 0, 'write_speed_kb': 0,
					'physical_drive': physical_drive
				}
		
		for drive_letter in ['C:\\', 'E:\\', 'F:\\']:
			if drive_letter not in disks:
				try:
					usage = psutil.disk_usage(drive_letter)
					disks[drive_letter] = {
						'total': round(usage.total / (1024**3), 2),
						'used': round(usage.used / (1024**3), 2),
						'free': round(usage.free / (1024**3), 2),
						'percent': usage.percent,
						'read_speed_mb': 0,
						'write_speed_mb': 0,
						'read_speed_kb': 0,
						'write_speed_kb': 0,
						'physical_drive': 'unknown'
					}
				except:
					pass
		
		self.last_disk_time = current_time
		
		hourly_upload, hourly_download = await self.track_network_usage()
		current_upload = net_up_history[-1] if net_up_history and len(net_up_history) > 0 else 0
		current_download = net_down_history[-1] if net_down_history and len(net_down_history) > 0 else 0
		
		gpu_usage = 0
		gpu_temp = await self._get_gpu_temp()
		try:
			gpus = GPUtil.getGPUs()
			if gpus:
				gpu_usage = gpus[0].load * 100
		except:
			pass
		
		servers = [
			{"name": "SCUM", "executable": "SCUMServer.exe", "port": 7042},
			{"name": "Minecraft", "executable": "java.exe", "port": 25565},
			{"name": "Rust", "executable": "RustDedicated.exe", "port": 28015},
			{"name": "DayZ", "executable": "DayZServer_x64.exe", "port": 2302},
		]
		
		server_status = {}
		for server in servers:
			server_status[server["name"]] = {
				"running": check_server_process(server["executable"]),
				"port": server["port"]
			}
		
		public_ip = await get_public_ip()
		local_ip = get_local_ip()
		
		bot_uptime = datetime.now() - bot_start_time
		uptime_seconds = bot_uptime.total_seconds()
		
		return {
			"cpu": {"percent": cpu_percent, "cores": psutil.cpu_count(logical=True)},
			"memory": {"percent": memory_percent, "used_gb": round(memory_used, 2), "total_gb": round(memory_total, 2)},
			"gpu": {"percent": gpu_usage, "temperature": gpu_temp},
			"temperatures": {"gpu": gpu_temp},
			"disks": disks,
			"network": {
				"upload_mb": current_upload,
				"download_mb": current_download,
				"upload_speed_mbps": round(current_upload * 8, 2),
				"download_speed_mbps": round(current_download * 8, 2),
				"hourly_upload_mb": round(hourly_upload, 2),
				"hourly_download_mb": round(hourly_download, 2)
			},
			"ip": {"public": public_ip if public_ip else "Unknown", "local": local_ip if local_ip else "Unknown"},
			"servers": server_status,
			"bot": {"uptime": uptime_seconds, "code_lines": code_line_count, "update_count": update_counter},
			"timestamp": datetime.now().isoformat()
		}

	async def _get_gpu_temp(self):
		"""Get GPU temperature"""
		try:
			gpus = GPUtil.getGPUs()
			if gpus:
				return gpus[0].temperature
		except:
			try:
				import subprocess
				if platform.system() == "Windows":
					result = subprocess.run(
						['nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader'],
						capture_output=True, text=True
					)
					if result.returncode == 0:
						return float(result.stdout.strip())
			except:
				pass
		return None

	async def broadcast_system_data(self):
		"""Broadcast system data to all connected WebSocket clients"""
		while True:
			try:
				if self.websocket_clients:
					data = await self.get_system_data()
					message = json.dumps(data)
					
					disconnected = set()
					for client in self.websocket_clients:
						try:
							await client.send(message)
						except:
							disconnected.add(client)
					
					for client in disconnected:
						self.websocket_clients.remove(client)
			
			except Exception as e:
				print(f"WebSocket broadcast error: {e}")
			
			await asyncio.sleep(1)


	# ============================================================================
	# WEBSITE AUTHENTICATION & FILE MANAGEMENT
	# ============================================================================

	async def handle_index(self, request):
		"""Serve login page or dashboard based on auth"""
		print(f"📄 Index request from {request.remote}")
		
		session_token = request.cookies.get('dashboard_token')
		print(f"🔍 Session token: {session_token}")
		print(f"📋 Active sessions: {list(self.active_sessions.keys())[:3]}...")
		
		if session_token in self.active_sessions:
			session_data = self.active_sessions[session_token]
			session_age = (datetime.now() - session_data['created']).total_seconds()
			print(f"✅ Valid session for {session_data['username']}, age: {session_age:.0f}s")
			
			if session_age < 86400:
				print(f"📊 Serving dashboard to {session_data['username']}")
				return web.FileResponse(r'E:\..SERVERS\_SERVERBOT\NOVA_WEBSITE\dashboard.html')
			else:
				print(f"⏰ Session expired for {session_data['username']}")
				del self.active_sessions[session_token]
		
		print("🔒 Serving login page")
		return web.FileResponse(r'E:\..SERVERS\_SERVERBOT\NOVA_WEBSITE\login.html')

	async def handle_login(self, request):
		"""Process login form"""
		print(f"🔐 Login attempt from {request.remote}")
		
		try:
			data = await request.post()
			username = data.get('username', '').strip()
			password = data.get('password', '').strip()
			
			print(f"📝 Username: '{username}', Password length: {len(password)}")
			
			if await self.verify_password(username, password):
				print(f"✅ Valid credentials for {username}")
				
				session_token = secrets.token_urlsafe(32)
				self.active_sessions[session_token] = {
					'username': username,
					'ip': request.remote,
					'created': datetime.now()
				}
				
				print(f"🎫 Created session token: {session_token[:10]}...")
				print(f"📊 Total active sessions: {len(self.active_sessions)}")
				
				response = web.HTTPFound('/')
				response.set_cookie('dashboard_token', session_token, 
								httponly=True, 
								max_age=86400,
								secure=False,
								samesite='Lax')
				
				print(f"🍪 Cookie set, redirecting to /")
				return response
			else:
				print(f"❌ Invalid credentials for {username}")
				return web.Response(
					text='<html><body>Invalid credentials. <a href="/">Try again</a></body></html>',
					content_type='text/html',
					status=401
				)
		
		except Exception as e:
			print(f"🔥 Login error: {e}")
			return web.Response(text=f"Server error: {str(e)}", status=500)

	async def handle_logout(self, request):
		"""Logout user"""
		session_token = request.cookies.get('dashboard_token')
		if session_token in self.active_sessions:
			del self.active_sessions[session_token]
		
		response = web.HTTPFound('/login.html')
		response.del_cookie('dashboard_token')
		return response

	async def verify_password(self, username, password):
		"""Verify against password file - NO AUTO-CREATION"""
		try:
			if not os.path.exists(PASSWORD_FILE):
				print(f"❌ Password file not found: {PASSWORD_FILE}")
				print("🔐 Please create it manually with:")
				print(f"   echo 'username:sha256_hash' > {PASSWORD_FILE}")
				print("   Generate hash: echo -n 'yourpassword' | sha256sum")
				return False
			
			password_hash = hashlib.sha256(password.encode()).hexdigest()
			
			with open(PASSWORD_FILE, 'r') as f:
				for line in f:
					line = line.strip()
					if not line or line.startswith('#'):
						continue
					
					if ':' in line:
						stored_user, stored_hash = line.split(':', 1)
						if stored_user.strip() == username.strip() and stored_hash.strip() == password_hash:
							return True
			
			return False
		
		except Exception as e:
			print(f"🔐 Password verification error: {e}")
			return False

	async def websocket_auth_middleware(self, request):
		"""Verify WebSocket connections have valid session"""
		session_token = request.query.get('token') or request.cookies.get('dashboard_token')
		
		if session_token not in self.active_sessions:
			raise web.HTTPForbidden()
		
		return True

	async def secure_websocket_handler(self, request):
		"""WebSocket with authentication"""
		try:
			await self.websocket_auth_middleware(request)
		except web.HTTPForbidden:
			return web.Response(status=403, text="Authentication required")
		
		ws = web.WebSocketResponse()
		await ws.prepare(request)
		
		self.websocket_clients.add(ws)
		
		try:
			system_data = await self.get_system_data()
			await ws.send_json(system_data)
			
			while True:
				await asyncio.sleep(1)
				system_data = await self.get_system_data()
				await ws.send_json(system_data)
		
		except Exception as e:
			print(f"WebSocket error: {e}")
		finally:
			if ws in self.websocket_clients:
				self.websocket_clients.remove(ws)
		
		return ws

	async def handle_upload(self, request):
		"""Handle file uploads from the website"""
		session_token = None
		file_path = None
		
		try:
			session_token = request.cookies.get('dashboard_token')
			if session_token not in self.active_sessions:
				return web.Response(status=403, text="Unauthorized")
			
			data = await request.post()
			file_item = data.get('file')
			if not file_item:
				return web.Response(
					status=400, 
					text=json.dumps({'success': False, 'error': 'No file provided'}),
					content_type='application/json'
				)
			
			file_type = data.get('type', 'screenshot')
			description = data.get('description', '')
			game = data.get('game', 'Unknown')
			
			print(f"📋 Upload metadata - Type: {file_type}, Game: {game}")
			print(f"📝 Description: {description[:50]}..." if description else "📝 Description: (empty)")
			
			if file_type == 'clip':
				dest_dir = self.clips_dir
				allowed_extensions = self.allowed_video_extensions
			else:
				dest_dir = self.screenshots_dir
				allowed_extensions = self.allowed_image_extensions
			
			filename = file_item.filename
			if not filename:
				return web.Response(
					status=400, 
					text=json.dumps({'success': False, 'error': 'No filename provided'}),
					content_type='application/json'
				)
			
			_, ext = os.path.splitext(filename.lower())
			if ext not in allowed_extensions:
				return web.Response(
					status=400, 
					text=json.dumps({'success': False, 'error': f"Invalid file type '{ext}'"}),
					content_type='application/json'
				)
			
			timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
			game_safe = re.sub(r'[^\w\-_\. ]', '', game)[:50]
			safe_filename = f"{timestamp}_{game_safe}_{filename}"
			safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in "._- ")
			
			file_path = os.path.join(dest_dir, safe_filename)
			file_content = file_item.file.read()
			file_size = len(file_content)
			
			with open(file_path, 'wb') as f:
				f.write(file_content)
			
			print(f"✅ File saved: {self._human_size(file_size)}")
			
			metadata = {
				'filename': safe_filename,
				'original_name': filename,
				'type': file_type,
				'game': game,
				'description': description,
				'uploaded_by': self.active_sessions[session_token]['username'],
				'uploaded_at': datetime.now().isoformat(),
				'size_bytes': file_size,
				'size_human': self._human_size(file_size)
			}
			
			meta_path = os.path.join(dest_dir, f"{safe_filename}.json")
			with open(meta_path, 'w') as f:
				json.dump(metadata, f, indent=2)
			
			print(f"📄 Metadata saved")
			
			return web.Response(
				text=json.dumps({
					'success': True, 
					'filename': safe_filename,
					'size': metadata['size_human'],
					'description': description
				}),
				content_type='application/json'
			)
		
		except Exception as e:
			print(f"🔥 Upload error: {e}")
			import traceback
			traceback.print_exc()
			
			if file_path and os.path.exists(file_path):
				try:
					os.remove(file_path)
					print(f"🧹 Cleaned up partial file")
				except:
					pass
			
			return web.Response(
				status=500, 
				text=json.dumps({'success': False, 'error': str(e)}),
				content_type='application/json'
			)

	async def handle_list_files(self, request):
		"""Return list of files with metadata"""
		try:
			session_token = request.cookies.get('dashboard_token')
			if session_token not in self.active_sessions:
				return web.Response(status=403, text="Unauthorized")
			
			file_type = request.query.get('type', 'screenshot')
			files = []
			
			if file_type == 'all':
				directories = [self.screenshots_dir, self.clips_dir]
				for dir_path in directories:
					for filename in os.listdir(dir_path):
						if filename.lower().endswith('.json'):
							continue
						
						file_path = os.path.join(dir_path, filename)
						meta_path = os.path.join(dir_path, f"{filename}.json")
						stat = os.stat(file_path)
						
						item_type = 'screenshot' if dir_path == self.screenshots_dir else 'clip'
						
						file_info = {
							'name': filename,
							'type': item_type,
							'size': self._human_size(stat.st_size),
							'size_human': self._human_size(stat.st_size),
							'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
							'url': f'/files/{item_type}/{filename}',
							'thumbnail': f'/files/{item_type}/{filename}' if item_type == 'screenshot' else None
						}
						
						if os.path.exists(meta_path):
							try:
								with open(meta_path, 'r') as f:
									metadata = json.load(f)
									file_info.update(metadata)
							except Exception as e:
								print(f"Error reading metadata {meta_path}: {e}")
						
						files.append(file_info)
			else:
				if file_type == 'clip':
					source_dir = self.clips_dir
				else:
					source_dir = self.screenshots_dir
				
				for filename in os.listdir(source_dir):
					if filename.lower().endswith('.json'):
						continue
					
					file_path = os.path.join(source_dir, filename)
					meta_path = os.path.join(source_dir, f"{filename}.json")
					stat = os.stat(file_path)
					
					file_info = {
						'name': filename,
						'type': file_type,
						'size': self._human_size(stat.st_size),
						'size_human': self._human_size(stat.st_size),
						'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
						'url': f'/files/{file_type}/{filename}',
						'thumbnail': f'/files/{file_type}/{filename}' if file_type == 'screenshot' else None
					}
					
					if os.path.exists(meta_path):
						try:
							with open(meta_path, 'r') as f:
								metadata = json.load(f)
								file_info.update(metadata)
						except Exception as e:
							print(f"Error reading metadata {meta_path}: {e}")
					
					files.append(file_info)
			
			files.sort(key=lambda x: x.get('modified', ''), reverse=True)
			return web.Response(text=json.dumps(files), content_type='application/json')
		
		except Exception as e:
			print(f"List files error: {e}")
			return web.Response(status=500, text=f"Error: {str(e)}")

	async def handle_serve_file(self, request):
		"""Serve files from screenshots/clips directories"""
		try:
			session_token = request.cookies.get('dashboard_token')
			if session_token not in self.active_sessions:
				return web.Response(status=403, text="Unauthorized")
			
			file_type = request.match_info.get('type', 'screenshot')
			filename = request.match_info.get('filename')
			
			if file_type == 'clip':
				file_path = os.path.join(self.clips_dir, filename)
			else:
				file_path = os.path.join(self.screenshots_dir, filename)
			
			if not os.path.exists(file_path):
				return web.Response(status=404, text="File not found")
			
			return web.FileResponse(file_path)
		
		except Exception as e:
			print(f"Serve file error: {e}")
			return web.Response(status=500, text=f"Error: {str(e)}")

	async def handle_delete_file(self, request):
		"""Delete a file and its metadata"""
		try:
			session_token = request.cookies.get('dashboard_token')
			if session_token not in self.active_sessions:
				return web.Response(status=403, text="Unauthorized")
			
			file_type = request.query.get('type', 'screenshot')
			filename = request.query.get('filename')
			
			if not filename:
				return web.Response(status=400, text="Filename required")
			
			if file_type == 'clip':
				file_path = os.path.join(self.clips_dir, filename)
				meta_path = os.path.join(self.clips_dir, f"{filename}.json")
			else:
				file_path = os.path.join(self.screenshots_dir, filename)
				meta_path = os.path.join(self.screenshots_dir, f"{filename}.json")
			
			deleted = []
			if os.path.exists(file_path):
				os.remove(file_path)
				deleted.append('file')
			
			if os.path.exists(meta_path):
				os.remove(meta_path)
				deleted.append('metadata')
			
			return web.Response(
				text=json.dumps({'success': True, 'deleted': deleted}),
				content_type='application/json'
			)
		
		except Exception as e:
			print(f"Delete error: {e}")
			return web.Response(status=500, text=f"Error: {str(e)}")

	def _human_size(self, size_bytes):
		"""Convert bytes to human readable format"""
		for unit in ['B', 'KB', 'MB', 'GB']:
			if size_bytes < 1024.0:
				return f"{size_bytes:.1f} {unit}"
			size_bytes /= 1024.0
		return f"{size_bytes:.1f} TB"


	# ============================================================================
	# WEBSERVER MANAGEMENT
	# ============================================================================

	async def start_websocket_server(self):
		"""Start combined HTTP + WebSocket server with authentication"""
		try:
			app = web.Application(client_max_size=2 * 1024 * 1024 * 1024)
			
			app.router.add_get('/', self.handle_index)
			app.router.add_get('/login', self.handle_index)
			app.router.add_post('/login', self.handle_login)
			app.router.add_get('/logout', self.handle_logout)
			app.router.add_get('/ws', self.secure_websocket_handler)
			app.router.add_post('/upload', self.handle_upload)
			app.router.add_get('/files', self.handle_list_files)
			app.router.add_get('/files/{type}/{filename}', self.handle_serve_file)
			app.router.add_delete('/files', self.handle_delete_file)
			app.router.add_post('/api/start-server', self.handle_start_server)
			
			website_path = config.WEBSITE_BASE
			app.router.add_static('/', website_path)
			
			runner = web.AppRunner(app, access_log=None, handle_signals=True, shutdown_timeout=1800)
			await runner.setup()
			
			site = web.TCPSite(runner, '0.0.0.0', 8080, reuse_address=True)
			await site.start()
			
			print(f"✅ Secure HTTP+WebSocket server on http://0.0.0.0:8080")
			print(f"   • 2GB upload limit enabled")
			print(f"   • Zero-RAM streaming uploads")
			print(f"   • 30-minute timeout for large uploads")
			print(f"   • Login required for access")
			
			import socket
			try:
				hostname = socket.gethostname()
				local_ip = socket.gethostbyname(hostname)
				print(f"📡 Access via: http://{local_ip}:8080")
			except:
				pass
		
		except Exception as e:
			print(f"❌ Failed to start server: {e}")
			import traceback
			traceback.print_exc()

	async def network_tracking_loop(self):
		"""Background task to track network usage every second"""
		while True:
			await self.track_network_usage()
			await asyncio.sleep(1)


	# ============================================================================
	# BOT LIFECYCLE MANAGEMENT
	# ============================================================================

	async def on_ready(self):
		"""Bot startup initialization"""
		print(f'Logged in as {self.user}')
		
		update_server_status.start()
		
		if not self.weekly_backup_check.is_running():
			self.weekly_backup_check.start()
		
		asyncio.create_task(self.network_tracking_loop())
		asyncio.create_task(self.start_websocket_server())
		asyncio.create_task(self.broadcast_system_data())
		
		print("✅ All systems started successfully!")

	async def close(self):
		"""Clean shutdown of bot"""
		self.voice_listening = False
		await super().close()

	async def on_voice_state_update(self, member, before, after):
		"""Auto-disconnect from voice when alone"""
		if member != self.user:
			voice_client = member.guild.voice_client
			if voice_client and len(voice_client.channel.members) == 1:
				await voice_client.disconnect()

# Start the bot
bot = HectorBot(command_prefix="!", intents=intents)






































# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def count_characters(file_path):
	"""Count total characters in a file"""
	count = 0
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			content = f.read()
			count = len(content)
	except Exception as e:
		print(f"Error reading file for character count: {e}")
	return count

def count_code_lines(file_path):
	"""Count non-comment, non-empty lines of code"""
	count = 0
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			for line in f:
				line_strip = line.strip()
				if line_strip and not line_strip.startswith("#"):
					count += 1
	except Exception as e:
		print(f"Error reading file for code lines: {e}")
	return count

def progress_bar(percent, length=10):
	"""Create colored progress bar with gradient"""
	bar_filled = int(percent / 100 * length)
	bar = []
	for i in range(length):
		if i < bar_filled:
			if i < 2:
				bar.append("🟦")
			elif i < 6 * length // 10:
				bar.append("🟩")
			elif i < 8 * length // 10:
				bar.append("🟨")
			else:
				bar.append("🟥")
		else:
			bar.append("⬛")
	return "".join(bar)

def format_uptime(delta):
	"""Format timedelta to hours/minutes/seconds"""
	hours, remainder = divmod(int(delta.total_seconds()), 3600)
	minutes, seconds = divmod(remainder, 60)
	return f"{hours}h {minutes}m {seconds}s"


# ============================================================================
# DASHBOARD UPDATE TASK
# ============================================================================

@tasks.loop(seconds=30)
async def update_server_status():
	"""Update Discord dashboard embed - Compact with Full Names"""
	global update_counter, code_line_count
	
	try:
		update_counter += 1
		
		code_line_count = count_code_lines(bot_file_path)
		char_count = count_characters(bot_file_path)
		
		servers = [
			{"name": "Valheim",   "executable": "valheim_server.exe", "ip": config.SERVER_IP, "port": 2456,  "password": ""},
			{"name": "DayZ",      "executable": "DayZServer_x64.exe", "ip": config.SERVER_IP, "port": 2302,  "password": ""},
			{"name": "Minecraft", "executable": "java.exe",           "ip": config.SERVER_IP, "port": 25565, "password": ""},
			{"name": "Rust",      "executable": "RustDedicated.exe",  "ip": config.SERVER_IP, "port": 28015, "password": ""},
			{"name": "SCUM",      "executable": "SCUMServer.exe",     "ip": config.SERVER_IP, "port": 7042,  "password": ""},
		]
		
		# Calculate backup size
		backup_total = 0
		for srv in servers:
			backup_folder = os.path.join(backup_root, srv['name'].upper())
			if os.path.exists(backup_folder):
				for dirpath, dirnames, filenames in os.walk(backup_folder):
					for f in filenames:
						try:
							backup_total += os.path.getsize(os.path.join(dirpath, f))
						except Exception:
							continue
		
		backup_gb = backup_total / 1e9
		
		# Create dark theme embed
		embed = discord.Embed(
			title=f"🖥️ **NOVA v{BOT_ver}** • Every 30s",
			color=0x89b4fa,  # Linux blue
			timestamp=datetime.now()
		)
		
		# TOP ROW: System Dashboard with Bot Stats
		uptime_delta = datetime.now() - bot_start_time
		uptime_str = format_uptime(uptime_delta)
		public_ip = await get_public_ip()
		
		dashboard_content = (
			f"⏱️ `{uptime_str}` • 🌍 `{public_ip or '...'}`\n"
			f"**BOT STATS**\n"
			f"Lines: `{code_line_count}` • Chars: `{char_count:,}`"
		)
		
		embed.add_field(
			name="📊 **SYSTEM DASHBOARD**",
			value=dashboard_content,
			inline=False
		)
		
		# SERVER STATUS: Horizontal with full names
		server_line = ""
		for srv in servers:
			is_running = check_server_process(srv['executable'])
			status_icon = "🟢" if is_running else "🔴"
			server_line += f"{status_icon} `{srv['name']}` "
		
		server_line += f"\n📁 **BACKUPS:** `{backup_gb:.1f}GB`"
		
		embed.add_field(
			name="🎮 **SERVER STATUS**",
			value=server_line,
			inline=False
		)
		
		# CONTROL PANEL with clean URL
		website_url = "https://benedictory-postaxially-aretha.ngrok-free.dev/"
		
		controls_content = (
			f"**WEBSITE:** `Online` • 🔗 [Click Here]({website_url}) • **Ver:** `BETA 0.8`\n"
			f"**CONTROLS:** `Click buttons below`"
		)
		
		embed.add_field(
			name="🔧 **CONTROL PANEL**",
			value=controls_content,
			inline=False
		)
		
		# Footer with GitHub only
		github_url = "https://github.com/Neks-Git"
		embed.set_footer(
			text=f"Made by [NeKs]({github_url})",
			icon_url="https://cdn.discordapp.com/emojis/1106366380393107476.gif"
		)
		
		# Horizontal button row with full names
		class DashboardView(discord.ui.View):
			def __init__(self):
				super().__init__(timeout=None)
				
				for srv in servers:
					is_running = check_server_process(srv['executable'])
					
					button = discord.ui.Button(
						label=srv['name'],
						style=discord.ButtonStyle.primary if not is_running else discord.ButtonStyle.danger,
						custom_id=f"start_{srv['name'].lower()}",
						emoji="▶️" if not is_running else "⏹️"
					)
					self.add_item(button)
		
		# Send/update message
		channel = bot.get_channel(bot.status_channel_id)
		if not channel:
			return
		
		message_id = load_message_id()
		try:
			message = await channel.fetch_message(message_id) if message_id else None
		except discord.NotFound:
			message = None
		
		if message:
			await message.edit(embed=embed, view=DashboardView())
		else:
			new_message = await channel.send(embed=embed, view=DashboardView())
			save_message_id(new_message.id)
		
	except Exception as e:
		print(f"Exception in update_server_status: {e}")

# ============================================================================
# INTERACTION HANDLER
# ============================================================================

@bot.listen()
async def on_interaction(interaction: discord.Interaction):
	"""Handle dashboard button interactions for server control panels"""
	if not interaction.data or "custom_id" not in interaction.data:
		return

	custom_id = interaction.data["custom_id"]
	
	# Handle start buttons from dashboard
	if custom_id.startswith("start_"):
		server_name = custom_id.split("_")[1].upper()
		cmd_channel = bot.get_channel(REMINDER_CHANNEL_ID)
		
		if not cmd_channel:
			await interaction.response.send_message(
				"❌ Commands channel not found!",
				ephemeral=True
			)
			return

		servers_info = [
			{"name": "Valheim",   "executable": "valheim_server.exe", "ip": EXPECTED_PUBLIC_IP, "port": 2456,  "password": ""},
			{"name": "DayZ",      "executable": "DayZServer_x64.exe", "ip": EXPECTED_PUBLIC_IP, "port": 2302,  "password": ""},
			{"name": "Minecraft", "executable": "java.exe",           "ip": EXPECTED_PUBLIC_IP, "port": 25565, "password": ""},
			{"name": "Rust",      "executable": "RustDedicated.exe",  "ip": EXPECTED_PUBLIC_IP, "port": 28015, "password": ""},
			{"name": "SCUM",      "executable": "SCUMServer.exe",     "ip": EXPECTED_PUBLIC_IP, "port": 7042,  "password": ""},
		]
		
		server_info = None
		for s in servers_info:
			if s["name"].lower() == server_name.lower():
				server_info = s
				break

		# Track max values for this server session
		class ServerStats:
			def __init__(self):
				self.max_cpu = 0
				self.max_ram = 0
				self.start_time = pytime.time()
				self.cpu_history = []
				self.ram_history = []
			
			def update(self, cpu, ram):
				self.cpu_history.append(cpu)
				self.ram_history.append(ram)
				if cpu > self.max_cpu:
					self.max_cpu = cpu
				if ram > self.max_ram:
					self.max_ram = ram
				if len(self.cpu_history) > 30:
					self.cpu_history.pop(0)
				if len(self.ram_history) > 30:
					self.ram_history.pop(0)
			
			def get_avg_cpu(self):
				return sum(self.cpu_history) / len(self.cpu_history) if self.cpu_history else 0
			
			def get_avg_ram(self):
				return sum(self.ram_history) / len(self.ram_history) if self.ram_history else 0

		async def create_control_embed(stats):
			is_running = check_server_process(server_info['executable'])
			
			system_ram = psutil.virtual_memory()
			total_system_ram_gb = system_ram.total / 1024**3
			
			cpu_cores = psutil.cpu_count(logical=True)
			
			server_cpu_usage = 0
			server_ram_usage_gb = 0
			server_cpu_percent = 0
			server_ram_percent = 0
			
			if is_running:
				for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_info', 'memory_percent']):
					if server_info['executable'].lower() in proc.info['name'].lower():
						server_cpu_usage = proc.info['cpu_percent']
						server_ram_usage_bytes = proc.info['memory_info'].rss
						server_ram_usage_gb = server_ram_usage_bytes / 1024**3
						server_ram_percent = (server_ram_usage_bytes / system_ram.total) * 100
						server_cpu_percent = server_cpu_usage / cpu_cores
						break
			
			stats.update(server_cpu_percent, server_ram_usage_gb)
			
			def create_ascii_graph(value, max_value=100, width=12):
				filled = min(int((value / max_value) * width), width)
				return "█" * filled + "░" * (width - filled)
			
			cpu_graph = create_ascii_graph(server_cpu_percent, 100, 12)
			ram_percent_graph = create_ascii_graph(server_ram_percent, 100, 12)
			
			embed = discord.Embed(
				title=f"🛠️ {server_name} Server Controls",
				description=(
					f"**IP:** `{server_info['ip']}:{server_info['port']}`\n"
					f"**Password:** `{server_info['password'] or 'None'}`\n"
					f"**Auto-updates every 60 seconds**"
				),
				color=0x00ff00 if is_running else 0xe74c3c,
				timestamp=datetime.now()
			)
			
			status_icon = "🟢" if is_running else "🔴"
			status_text = "**Online**" if is_running else "**Offline**"
			
			cpu_field_value = (
				f"{status_text}\n"
				f"**Current:** `{server_cpu_percent:.1f}%` {cpu_graph}\n"
				f"**Per Core:** `{server_cpu_usage:.1f}%`\n"
				f"**Session Avg:** `{stats.get_avg_cpu():.1f}%`\n"
				f"**Session Max:** `{stats.max_cpu:.1f}%`\n"
				f"**CPU Cores:** `{cpu_cores}` available"
			)
			
			ram_field_value = (
				f"**Server RAM:** `{server_ram_usage_gb:.2f} GB` {ram_percent_graph}\n"
				f"**RAM % of System:** `{server_ram_percent:.1f}%`\n"
				f"**Session Avg:** `{stats.get_avg_ram():.2f} GB`\n"
				f"**Session Max:** `{stats.max_ram:.2f} GB`\n"
				f"**Total System RAM:** `{total_system_ram_gb:.1f} GB`\n"
				f"**System Free:** `{(system_ram.available / 1024**3):.1f} GB`"
			)
			
			embed.add_field(
				name=f"{status_icon} CPU Usage",
				value=cpu_field_value,
				inline=True
			)
			
			embed.add_field(
				name="💾 RAM Usage",
				value=ram_field_value,
				inline=True
			)
			
			uptime_seconds = pytime.time() - stats.start_time
			hours = int(uptime_seconds // 3600)
			minutes = int((uptime_seconds % 3600) // 60)
			
			embed.add_field(
				name="📊 Session Stats",
				value=(
					f"**Uptime:** `{hours}h {minutes}m`\n"
					f"**Process:** `{server_info['executable']}`\n"
					f"**Port:** `{server_info['port']}`\n"
					f"**Data Points:** `{len(stats.cpu_history)}`"
				),
				inline=False
			)
			
			embed.set_footer(text=f"Last update: {datetime.now().strftime('%H:%M:%S')}")
			return embed

		class AutoUpdateControlPanel(discord.ui.View):
			def __init__(self, server_name, executable, channel_id):
				super().__init__(timeout=None)
				self.server_name = server_name
				self.executable = executable
				self.channel_id = channel_id
				self.message_id = None
				self.update_task = None
				self.stats = ServerStats()
			
			async def start_auto_update(self):
				await asyncio.sleep(2)
				async def update_loop():
					while True:
						try:
							await asyncio.sleep(60)
							await self.update_panel()
						except asyncio.CancelledError:
							break
						except Exception as e:
							print(f"[{self.server_name}] Update error: {e}")
							await asyncio.sleep(60)
				self.update_task = asyncio.create_task(update_loop())
			
			async def update_panel(self):
				try:
					channel = bot.get_channel(self.channel_id)
					if not channel or not self.message_id:
						return
					
					try:
						message = await channel.fetch_message(self.message_id)
					except discord.NotFound:
						return
					
					fresh_embed = await create_control_embed(self.stats)
					await message.edit(embed=fresh_embed)
					
				except Exception as e:
					print(f"[{self.server_name}] Panel update failed: {e}")
			
			@discord.ui.button(label="▶️ Start Server", style=discord.ButtonStyle.green)
			async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
				await interaction.response.defer(ephemeral=True)
				start_command = {
					"Valheim": "startvalheim",
					"DayZ": "startdayz",
					"Minecraft": "startminecraft",
					"Rust": "startrust",
					"SCUM": "startscum"
				}.get(self.server_name)

				if start_command:
					command = bot.get_command(start_command)
					if command:
						ctx = await bot.get_context(interaction.message)
						ctx.author = interaction.user
						await command(ctx)
						await asyncio.sleep(3)
						await self.update_panel()
						await interaction.followup.send("✅ Server started! Panel updating...", ephemeral=True)
					else:
						await interaction.followup.send("❌ Command not found!", ephemeral=True)
				else:
					await interaction.followup.send("❌ Unknown server!", ephemeral=True)

			@discord.ui.button(label="⏹️ Stop Server", style=discord.ButtonStyle.red)
			async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
				await interaction.response.defer(ephemeral=True)
				shutdown_command = {
					"Valheim": shutdownvalheim,
					"DayZ": shutdowndayz,
					"Minecraft": shutdownminecraft,
					"SCUM": shutdownscum
				}.get(self.server_name)

				if shutdown_command:
					ctx = await bot.get_context(interaction.message)
					ctx.author = interaction.user
					await shutdown_command(ctx)
					await asyncio.sleep(2)
					await self.update_panel()
					await interaction.followup.send("✅ Server stopped! Panel updating...", ephemeral=True)
				else:
					await interaction.followup.send("❌ Unknown server!", ephemeral=True)

			@discord.ui.button(label="💾 Create Backup", style=discord.ButtonStyle.blurple)
			async def backup(self, interaction: discord.Interaction, button: discord.ui.Button):
				await interaction.response.defer(ephemeral=True)
				backup_command = {
					"Valheim": backupvalheim,
					"DayZ": backupdayz,
					"Minecraft": backupminecraft,
					"SCUM": backupscum
				}.get(self.server_name)

				if backup_command:
					ctx = await bot.get_context(interaction.message)
					ctx.author = interaction.user
					await backup_command(ctx)
					await interaction.followup.send("✅ Backup created!", ephemeral=True)
				else:
					await interaction.followup.send("❌ Unknown server!", ephemeral=True)

			@discord.ui.button(label="🔄 Refresh Now", style=discord.ButtonStyle.gray)
			async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
				await interaction.response.defer(ephemeral=True)
				await self.update_panel()
				await interaction.followup.send("✅ Panel refreshed!", ephemeral=True)

			@discord.ui.button(label="📊 Reset Stats", style=discord.ButtonStyle.gray)
			async def reset_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
				await interaction.response.defer(ephemeral=True)
				self.stats = ServerStats()
				await self.update_panel()
				await interaction.followup.send("✅ Session stats reset!", ephemeral=True)

		view_instance = AutoUpdateControlPanel(
			server_name, 
			server_info["executable"], 
			cmd_channel.id
		)
		
		initial_embed = await create_control_embed(view_instance.stats)
		control_message = await cmd_channel.send(
			embed=initial_embed,
			view=view_instance
		)
		
		view_instance.message_id = control_message.id
		asyncio.create_task(view_instance.start_auto_update())
		
		await interaction.response.send_message(
			f"✅ **{server_name}** control panel created!\n"
			f"It will auto-update every 60 seconds with detailed CPU/RAM stats.",
			ephemeral=True
		)







# ── START: backup checking ───────────────────────────  





def get_latest_valheim_backups(path):
	"""Returns the latest Valheim backup pair: game + world"""
	try:
		backups = {}
		for f in os.listdir(path):
			full_path = os.path.join(path, f)
			if os.path.isdir(full_path) and f.startswith("backup_"):
				date_key = f.replace("_world", "")
				backups.setdefault(date_key, []).append(full_path)
		
		# Pick the latest based on date_key modification time
		latest = max(
			backups.items(), 
			key=lambda item: max(os.path.getmtime(p) for p in item[1])
		) if backups else None

		return latest[1] if latest else None
	except:
		return None

def get_latest_backup(path):
	"""Returns most recent backup folder with improved filtering"""
	try:
		backups = [
			os.path.join(path, f) 
			for f in os.listdir(path) 
			if os.path.isdir(os.path.join(path, f)) 
			and f.startswith("backup_")
		]
		return max(backups, key=os.path.getmtime) if backups else None
	except:
		return None

def get_folder_size(path):
	"""Returns folder size in bytes with error handling"""
	total_size = 0
	for root, _, files in os.walk(path):
		for f in files:
			try:
				total_size += os.path.getsize(os.path.join(root, f))
			except:
				continue
	return total_size

def verify_backup_integrity(folder):
    """Only check for unreadable files (true corruption)"""
    corrupt = []
    
    for root, _, files in os.walk(folder):
        for file in files:
            filepath = os.path.join(root, file)
            
            # Skip obviously harmless files
            if file.endswith(('.log', '.tmp', '.cache', '.bak')):
                continue
                
            try:
                # Just try to open and read a tiny bit
                with open(filepath, 'rb') as f:
                    # Try to read first 4 bytes
                    f.read(4)
                    
                # Also check file size for very small files
                # (empty or tiny files are often OK)
                if os.path.getsize(filepath) < 1024:  # Less than 1KB
                    continue
                    
            except (IOError, OSError, PermissionError) as e:
                # Only mark as corrupt if it's not a permission issue
                if "Permission" not in str(e):
                    corrupt.append(file)
            except Exception as e:
                # Any other error is suspicious
                corrupt.append(f"{file} - {type(e).__name__}")
    
    return corrupt

async def run_chkdsk_preview_async(drive):
	"""Run CHKDSK safely in a thread"""
	def run():
		try:
			result = subprocess.run(
				f"chkdsk {drive} /scan",
				capture_output=True,
				text=True,
				shell=True,
				timeout=240
			)
			output = result.stdout
			end_index = output.find("Windows has scanned the file system")
			return output[end_index:].strip() if end_index != -1 else output
		except subprocess.TimeoutExpired:
			return "CHKDSK scan timed out after 240s"
		except Exception as e:
			return f"CHKDSK scan failed: {str(e)}"
	return await asyncio.to_thread(run)

async def check_valheim_pairs(ctx):
	"""Ensure world+game backups exist together (with embed)"""
	config = BACKUP_CONFIG["Valheim"]
	backups = {}

	for f in os.listdir(config['backup_dir']):
		if f.startswith("backup_"):
			date_key = f[:-6] if f.endswith("_world") else f
			backups.setdefault(date_key, []).append(f)

	missing_pairs = []
	for date_key, files in backups.items():
		if len(files) < 2:
			missing_pairs.append(date_key)

	pair_embed = discord.Embed(
		title="Valheim Backup Pairs",
		color=discord.Color.red() if missing_pairs else discord.Color.green()
	)
	
	if missing_pairs:
		pair_embed.description = "⚠️ Missing backup pairs for:"
		pair_embed.add_field(
			name="Incomplete Backups",
			value="\n".join(missing_pairs),
			inline=False
		)
	else:
		pair_embed.description = "✅ All Valheim backups are correctly paired"

	await ctx.send(embed=pair_embed)

@bot.command()
async def checkbackups(ctx):
	"""Run comprehensive backup health check with embeds"""
	try:
		# Configuration
		BACKUP_DRIVE = "F:"
		BACKUP_PATHS = {
			"Valheim Server": r"F:\GAMEBACKUPS\VALHEIM",
			"DayZ": r"F:\GAMEBACKUPS\DAYZ",
			"Minecraft": r"F:\GAMEBACKUPS\MINECRAFT",
			"7 Days to Die": r"F:\GAMEBACKUPS\7DTD",
			"Discord Bot": r"F:\GAMEBACKUPS\BOT",
			"Divinity: Original Sin 2": r"F:\GAMEBACKUPS\DOS2",
			"Rust": r"F:\GAMEBACKUPS\RUST",
			"SCUM": r"F:\GAMEBACKUPS\SCUM"
		}

		# Initial status embed
		status_embed = discord.Embed(
			title="🔎 Backup Health Check",
			description="Starting verification...",
			color=discord.Color.blue()
		)
		status_msg = await ctx.send(embed=status_embed)

		# 1. Drive Health Check
		disk = psutil.disk_usage(BACKUP_DRIVE)
		drive_embed = discord.Embed(
			title="💽 Backup Drive Health",
			color=discord.Color.green() if disk.percent < 85 else discord.Color.orange()
		)
		drive_embed.add_field(
			name=f"Drive {BACKUP_DRIVE}",
			value=f"```diff\n+ Total: {disk.total/1024**3:.1f} GB\n+ Used: {disk.used/1024**3:.1f} GB\n+ Free: {disk.free/1024**3:.1f} GB\n```",
			inline=False
		)
		await ctx.send(embed=drive_embed)

		# 2. Backup Integrity Check
		backup_embed = discord.Embed(
			title="🔍 Backup Integrity",
			color=discord.Color.blue()
		)
		corrupt_count = 0

		for name, path in BACKUP_PATHS.items():
			status_embed.description = f"Checking {name}..."
			await status_msg.edit(embed=status_embed)

			if not os.path.exists(path):
				backup_embed.add_field(
					name=f"❌ {name}",
					value="Path not found",
					inline=False
				)
				continue

			if name == "Valheim Server":
				valheim_backups = get_latest_valheim_backups(path)
				if not valheim_backups:
					backup_embed.add_field(
						name=f"⚠️ {name}",
						value="No backups found",
						inline=False
					)
					continue

				for bpath in valheim_backups:
					backup_name = os.path.basename(bpath)
					corrupt_files = await asyncio.to_thread(verify_backup_integrity, bpath)
					corrupt_count += len(corrupt_files)
					
					# Add corrupt file details if any
					corrupt_details = ""
					if corrupt_files:
						# Get first 5 corrupt file names
						first_five = [os.path.basename(f) for f in corrupt_files[:5]]
						corrupt_details = f"\n**Corrupt Files**: {', '.join(first_five)}"
						if len(corrupt_files) > 5:
							corrupt_details += f" (+{len(corrupt_files) - 5} more)"
					
					backup_embed.add_field(
						name=f"📂 {name} ({'World' if '_world' in backup_name else 'Server'})",
						value=(
							f"**Name**: {backup_name}\n"
							f"**Size**: {get_folder_size(bpath)/1024**2:.1f} MB\n"
							f"**Status**: {'❌ Corrupt' if corrupt_files else '✅ Healthy'}\n"
							f"**Total Corrupt**: {len(corrupt_files)}"
							f"{corrupt_details}"
						),
						inline=True
					)
			else:
				latest_backup = get_latest_backup(path)
				if not latest_backup:
					backup_embed.add_field(
						name=f"⚠️ {name}",
						value="No backups found",
						inline=False
					)
					continue

				corrupt_files = await asyncio.to_thread(verify_backup_integrity, latest_backup)
				corrupt_count += len(corrupt_files)
				
				# Add corrupt file details if any
				corrupt_details = ""
				if corrupt_files:
					# Get first 5 corrupt file names
					first_five = [os.path.basename(f) for f in corrupt_files[:5]]
					corrupt_details = f"\n**Corrupt Files**: {', '.join(first_five)}"
					if len(corrupt_files) > 5:
						corrupt_details += f" (+{len(corrupt_files) - 5} more)"
				
				backup_embed.add_field(
					name=f"📂 {name}",
					value=(
						f"**Name**: {os.path.basename(latest_backup)}\n"
						f"**Size**: {get_folder_size(latest_backup)/1024**2:.1f} MB\n"
						f"**Status**: {'❌ Corrupt' if corrupt_files else '✅ Healthy'}\n"
						f"**Total Corrupt**: {len(corrupt_files)}"
						f"{corrupt_details}"
					),
					inline=True
				)

		await ctx.send(embed=backup_embed)

		# 3. File System Check
		status_embed.description = "Running file system check..."
		await status_msg.edit(embed=status_embed)
		fs_check = await run_chkdsk_preview_async(BACKUP_DRIVE)
		fs_embed = discord.Embed(
			title="🛠️ File System Check",
			description=f"```{fs_check[:1000]}```",
			color=discord.Color.blue()
		)
		await ctx.send(embed=fs_embed)

		# 4. Valheim Pair Check
		await check_valheim_pairs(ctx)

		# 5. Final Summary
		summary_embed = discord.Embed(
			title="📊 Backup Check Summary",
			color=discord.Color.green() if corrupt_count == 0 else discord.Color.orange(),
			timestamp=datetime.now()
		)
		summary_embed.add_field(
			name="Results",
			value=(
				f"**Games Checked**: {len(BACKUP_PATHS)}\n"
				f"**Corrupt Files Found**: {corrupt_count}\n"
				f"**Drive Space Used**: {disk.percent}%"
			),
			inline=False
		)
		await ctx.send(embed=summary_embed)

		# Update status to complete
		status_embed.description = "✅ Verification complete"
		status_embed.color = discord.Color.green()
		await status_msg.edit(embed=status_embed)

	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Backup Check Failed",
			description=f"```{str(e)}```",
			color=discord.Color.red()
		)
		await ctx.send(embed=error_embed)

		 
		
		
		
		
		
		
		
		
		






















# ============================================================================
# SERVER START COMMANDS
# ============================================================================

def run_server(bat_file_path):
	"""Start server process via batch file in new command window"""
	try:
		subprocess.Popen(f'start cmd /k "{bat_file_path}"', shell=True)
	except Exception as e:
		print(f"Error starting the server: {e}")

@bot.command()
async def startdayz(ctx):
	"""Start DayZ server with Discord embed updates"""
	server_directory = r'E:\SteamLibrary\steamapps\common\DayZServer'
	bat_file_path = os.path.join(server_directory, 'start.bat')
	
	embed = discord.Embed(
		title="DayZ Server Manager",
		description="Starting the DayZ dedicated server...",
		color=discord.Color.orange()
	)
	embed.add_field(name="Status", value="⚙️ Initializing...", inline=False)
	
	message = await ctx.send(embed=embed)
	
	try:
		subprocess.Popen(f'start cmd /k "{bat_file_path}"', shell=True, cwd=server_directory)
		embed.colour = discord.Color.gold()
		embed.set_field_at(0, name="Status", value="🚀 Launching server process...", inline=False)
		await message.edit(embed=embed)
		
		await asyncio.sleep(10)
		
		if check_server_process("DayZServer_x64.exe"):
			embed.colour = discord.Color.green()
			embed.set_field_at(0, name="Status", value="🟢 Server is running! Wait 1-2mins to join", inline=False)
			embed.add_field(
				name="Connection Info", 
				value="```Connect using: steam://connect/YOUR_SERVER_IP:2302```", 
				inline=False
			)
			embed.set_footer(text="")
		else:
			embed.colour = discord.Color.red()
			embed.set_field_at(0, name="Status", value="🔴 Server failed to start", inline=False)
			embed.add_field(
				name="Troubleshooting", 
				value="Please check:\n• Server logs\n• Port availability\n• System resources", 
				inline=False
			)
			embed.set_footer(text="Contact an admin if the issue persists")
		
		await message.edit(embed=embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Startup Error",
			description="An error occurred while starting the DayZ server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Error Details", value=f"```{str(e)}```", inline=False)
		await ctx.send(embed=error_embed)

@bot.command()
async def startvalheim(ctx):
	"""Start Valheim server with visual embed and connection info"""
	server_directory = r'E:\..SERVERS\VALHEIM'
	bat_file_path = os.path.join(server_directory, 'start_headless_server.bat')
	
	embed = discord.Embed(
		title="Valheim Server Manager",
		description="Starting the Valheim dedicated server...",
		color=discord.Color.orange()
	)
	embed.set_thumbnail(url="https://i.imgur.com/rkLRl6z.png")
	embed.add_field(name="Status", value="⚙️ Initializing...", inline=False)
	
	message = await ctx.send(embed=embed)
	
	try:
		subprocess.Popen(f'start cmd /k "{bat_file_path}"', shell=True, cwd=server_directory)
		embed.colour = discord.Color.gold()
		embed.set_field_at(0, name="Status", value="🚀 Launching server process...", inline=False)
		await message.edit(embed=embed)
		
		await asyncio.sleep(10)
		
		if check_server_process("valheim_server.exe"):
			embed.colour = discord.Color.green()
			embed.set_field_at(0, name="Status", value="🟢 Server is running! Wait 1-2mins to join", inline=False)
			embed.add_field(
				name="Connection Info", 
				value="```Connect using: steam://connect/{EXPECTED_PUBLIC_IP}```", 
				inline=False
			)
			embed.set_footer(text="")
		else:
			embed.colour = discord.Color.red()
			embed.set_field_at(0, name="Status", value="🔴 Server failed to start", inline=False)
			embed.add_field(
				name="Troubleshooting", 
				value="Please check:\n• Server logs\n• Port availability\n• System resources", 
				inline=False
			)
			embed.set_footer(text="Contact an admin if the issue persists")
		
		await message.edit(embed=embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Server Start Error",
			description="An error occurred while starting the server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server configuration")
		await message.edit(embed=error_embed)

@bot.command()
async def startminecraft(ctx):
	"""Start Minecraft (Fabric) server with Java optimization flags"""
	server_directory = r'E:\..SERVERS\MINECRAFT\Minecraft server'
	fabric_jar_path = r'fabric-server-launch.jar'
	
	embed = discord.Embed(
		title="Minecraft Server Manager",
		description="Starting the Minecraft (Fabric) server...",
		color=discord.Color.orange()
	)
	embed.set_thumbnail(url="https://i.imgur.com/MS1Tc3C.png")
	embed.add_field(name="Status", value="⚙️ Initializing...", inline=False)
	
	message = await ctx.send(embed=embed)
	
	try:
		command = f'java -XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:+UnlockExperimentalVMOptions -XX:G1NewSizePercent=40 -XX:G1MaxNewSizePercent=50 -XX:G1HeapRegionSize=16M -XX:G1ReservePercent=15 -XX:InitiatingHeapOccupancyPercent=20 -XX:+AlwaysPreTouch -jar {fabric_jar_path}'
		subprocess.Popen(f'start cmd /k "{command}"', shell=True, cwd=server_directory)
		embed.colour = discord.Color.gold()
		embed.set_field_at(0, name="Status", value="🚀 Launching server process...", inline=False)
		await message.edit(embed=embed)
		
		await asyncio.sleep(10)
		
		if check_server_process("java.exe"):
			embed.colour = discord.Color.green()
			embed.set_field_at(0, name="Status", value="🟢 Server is running!", inline=False)
			embed.add_field(
				name="Connection Info", 
				value="```Connect using: {EXPECTED_PUBLIC_IP}```", 
				inline=False
			)
			embed.set_footer(text="")
		else:
			embed.colour = discord.Color.red()
			embed.set_field_at(0, name="Status", value="🔴 Server failed to start", inline=False)
			embed.add_field(
				name="Troubleshooting", 
				value="Please check:\n• Server logs\n• Port availability\n• System resources", 
				inline=False
			)
			embed.set_footer(text="Contact an admin if the issue persists")
		
		await message.edit(embed=embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Server Start Error",
			description="An error occurred while starting the server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server configuration")
		await message.edit(embed=error_embed)

@bot.command()
async def startrust(ctx):
	"""Start Rust dedicated server with connection guidance"""
	server_directory = r'E:\..SERVERS\RUST\Server'
	bat_file_path = os.path.join(server_directory, 'Run_DS.bat')
	
	embed = discord.Embed(
		title="Rust Server Manager",
		description="Starting the Rust dedicated server...",
		color=discord.Color.orange()
	)
	embed.set_thumbnail(url="https://imgur.com/gallery/original-rust-game-logo-icon-WHYBfJy#znQvBMi")
	embed.add_field(name="Status", value="⚙️ Initializing...", inline=False)
	
	message = await ctx.send(embed=embed)
	
	try:
		subprocess.Popen(f'start cmd /k "{bat_file_path}"', shell=True, cwd=server_directory)
		embed.colour = discord.Color.gold()
		embed.set_field_at(0, name="Status", value="🚀 Launching server process...", inline=False)
		await message.edit(embed=embed)
		
		await asyncio.sleep(10)
		
		if check_server_process("RustDedicated.exe"):
			embed.colour = discord.Color.green()
			embed.set_field_at(0, name="Status", value="🟢 Server is running!", inline=False)
			embed.add_field(
				name="Connection Info",
				value="```Search for the server in Rust's server browser or connect via IP```",
				inline=False
			)
			embed.set_footer(text="")
		else:
			embed.colour = discord.Color.red()
			embed.set_field_at(0, name="Status", value="🔴 Server failed to start", inline=False)
			embed.add_field(
				name="Troubleshooting",
				value="Please check:\n• Server logs\n• Port availability\n• System resources",
				inline=False
			)
			embed.set_footer(text="Contact an admin if the issue persists")
		
		await message.edit(embed=embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Server Start Error",
			description="An error occurred while starting the server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server configuration")
		await message.edit(embed=error_embed)

@bot.command()
async def startscum(ctx):
	"""Start SCUM server with auto-delete success message after 30 seconds"""
	server_directory = r'C:\Program Files (x86)\Steam\steamapps\common\SCUM Server\SCUM\Binaries\Win64'
	bat_file_path = os.path.join(server_directory, 'start_server.bat')
	
	embed = discord.Embed(
		title="SCUM Server Manager",
		description="Starting the SCUM dedicated server...",
		color=discord.Color.orange()
	)
	embed.set_thumbnail(url="https://cdn2.steamgriddb.com/file/sgdb-cdn/icon_thumb/054f7d1bb8935ba473f5e6df91ee8ac6.png")
	embed.add_field(name="Status", value="⚙️ Initializing...", inline=False)
	
	message = await ctx.send(embed=embed)
	
	try:
		subprocess.Popen(f'start cmd /k "{bat_file_path}"', shell=True, cwd=server_directory)
		embed.colour = discord.Color.gold()
		embed.set_field_at(0, name="Status", value="🚀 Launching server process...", inline=False)
		await message.edit(embed=embed)
		
		await asyncio.sleep(10)
		
		if check_server_process("SCUMServer.exe"):
			embed.colour = discord.Color.green()
			embed.set_field_at(0, name="Status", value="🟢 Server is running!", inline=False)
			embed.add_field(
				name="⚠️ Important Note",
				value=(
					"It may take 2-3 minutes for the server to be fully ready.\n"
					"You can connect via server browser or IP.\n\n"
					"**This message will auto-delete in 30 seconds.**"
				),
				inline=False
			)
			embed.set_footer(text="Server control panel will auto-update with stats")
			
			await message.edit(embed=embed)
			await asyncio.sleep(30)
			await message.delete()
			
		else:
			embed.colour = discord.Color.red()
			embed.set_field_at(0, name="Status", value="🔴 Server failed to start", inline=False)
			embed.add_field(
				name="Troubleshooting",
				value="Please check:\n• Server logs\n• Port availability\n• System resources",
				inline=False
			)
			embed.set_footer(text="Contact an admin if the issue persists")
			await message.edit(embed=embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Server Start Error",
			description="An error occurred while starting the server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server configuration")
		await message.edit(embed=error_embed)
























# ============================================================================
# BACKUP SYSTEM
# ============================================================================

async def backup_server(source_dir, backup_dir, exclude_dirs=None, max_backups=4, label=None, all_backups=None, timestamp=None):
	"""Async wrapper for backup operations using thread pool"""
	if exclude_dirs is None:
		exclude_dirs = []
	
	return await asyncio.to_thread(
		_sync_backup_server,
		source_dir, backup_dir, exclude_dirs, max_backups, label, all_backups, timestamp
	)

def _sync_backup_server(source_dir, backup_dir, exclude_dirs, max_backups, label, all_backups, timestamp=None):
	"""Synchronous backup implementation with rotation and size tracking"""
	timestamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M")
	label_suffix = f"_{label}" if label else ""
	backup_folder = os.path.join(backup_dir, f"backup_{timestamp}{label_suffix}")

	try:
		os.makedirs(backup_folder, exist_ok=True)

		for item in os.listdir(source_dir):
			item_path = os.path.join(source_dir, item)

			if any(excluded_dir in item_path for excluded_dir in exclude_dirs):
				print(f"Skipping directory: {item}")
				continue

			if os.path.isdir(item_path):
				shutil.copytree(item_path, os.path.join(backup_folder, item))
			else:
				shutil.copy2(item_path, backup_folder)

		print(f"Backup completed: {backup_folder}")

		if all_backups:
			backups = sorted(
				[f for f in os.listdir(backup_dir) if f.startswith("backup_")],
				key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))
		else:
			backups = sorted(
				[f for f in os.listdir(backup_dir)
				if f.startswith("backup_") and f.endswith(label_suffix)],
				key=lambda f: os.path.getmtime(os.path.join(backup_dir, f)))

		deleted_backup = None
		while len(backups) > max_backups:
			oldest_backup = backups.pop(0)
			oldest_backup_path = os.path.join(backup_dir, oldest_backup)
			shutil.rmtree(oldest_backup_path)
			print(f"Deleted old backup: {oldest_backup_path}")
			deleted_backup = oldest_backup

		total_size = 0
		for dirpath, dirnames, filenames in os.walk(backup_folder):
			for f in filenames:
				file_path = os.path.join(dirpath, f)
				total_size += os.path.getsize(file_path)
		total_size_mb = total_size / (1024 * 1024)

		return backup_folder, deleted_backup, total_size_mb

	except Exception as e:
		print(f"Error during backup: {e}")
		return None, None, 0

async def run_backup(ctx, server_name, source_dir, backup_dir, exclude_dirs=None, max_backups=4):
	"""Run single server backup with Discord status updates"""
	if exclude_dirs is None:
		exclude_dirs = []

	initial_msg = await ctx.send(f"🚀 Starting {server_name} server backup...")

	try:
		backup_folder, deleted_backup, backup_size = await backup_server(
			source_dir, backup_dir, exclude_dirs, max_backups
		)

		if not backup_folder:
			await ctx.send(f"❌ Failed to backup {server_name} server")
			return

		total, used, free = shutil.disk_usage(backup_dir)
		free_gb = free // (2**30)

		message = (
			f"✅ **{server_name} Backup Completed**\n"
			f"🔹 Location: `{backup_folder}`\n"
			f"📦 Size: `{backup_size:.2f} MB`\n"
			f"💾 Remaining Disk Space: `{free_gb} GB`"
		)

		if deleted_backup:
			message += f"\n🗑️ Deleted old backup: `{deleted_backup}`"

		await initial_msg.edit(content=message)

	except Exception as e:
		await ctx.send(f"⚠️ {server_name} backup error: {str(e)}")

async def run_combined_backup(ctx, server_name, server_dir, world_dir, backup_dir, exclude_dirs=None, max_backups=4):
	"""Run combined server+world backup with visual Discord embeds"""
	embed = discord.Embed(
		title=f"🔁 {server_name} Backup In Progress",
		description="Please wait while we secure your game data...",
		color=0xf1c40f
	)
	embed.set_thumbnail(url="https://i.imgur.com/rkLRl6z.png")
	status_msg = await ctx.send(embed=embed)
	
	try:
		server_task = backup_server(
			server_dir, backup_dir, exclude_dirs, max_backups, None, True
		)
		world_task = backup_server(
			world_dir, backup_dir, exclude_dirs, max_backups, "world", True
		)
		
		server_backup, server_deleted, server_size = await server_task
		world_backup, world_deleted, world_size = await world_task
		
		server_verification = "✅ Verified" if not validate_backup_contents(server_backup, "server") else "⚠️ Verification issues"
		world_verification = "✅ Verified" if not validate_backup_contents(world_backup, "world") else "⚠️ Verification issues"
		
		result_embed = discord.Embed(
			title=f"✅ {server_name} Backup Complete",
			color=0x2ecc71
		)
		
		result_embed.add_field(
			name="Server Files",
			value=f"📦 `{server_backup}`\n"
				  f"📁  {server_size:.2f}MB\n"
				  f"{server_verification}",
			inline=True
		)
		
		result_embed.add_field(
			name="World Data",
			value=f"🌍 `{world_backup}`\n"
				  f"📁 {world_size:.2f}MB\n"
				  f"{world_verification}",
			inline=True
		)
		
		if server_deleted or world_deleted:
			cleanup = []
			if server_deleted:
				cleanup.append(f"🗑️ Server: `{server_deleted}`")
			if world_deleted:
				cleanup.append(f"🗑️ World: `{world_deleted}`")
				
			result_embed.add_field(
				name="Old Backups Removed",
				value="\n".join(cleanup),
				inline=False
			)
		
		await status_msg.edit(embed=result_embed)
		
	except Exception as e:
		error_embed = discord.Embed(
			title=f"❌ {server_name} Backup Failed",
			description=f"An error occurred: {str(e)}",
			color=0xe74c3c
		)
		await status_msg.edit(embed=error_embed)

BACKUP_CONFIG = {
	"Valheim": {
		"server_dir": r'E:\..SERVERS\VALHEIM',
		"world_dir": r'C:\Users\rekor\AppData\LocalLow\IronGate\Valheim',
		"backup_dir": r'F:\GAMEBACKUPS\VALHEIM',
		"max_backups": 4,
		"max_age_days": 3,
		"critical_files": {
			"world": ["worlds/*.fwl", "worlds/*.db"],
			"server": ["start_server.bat"]
		}
	},
	"DayZ": {
		"server_dir": r'E:\SteamLibrary\steamapps\common\DayZServer',
		"backup_dir": r'F:\GAMEBACKUPS\DAYZ',
		"exclude_dirs": [r'@RUSForma_vehicles'],
		"max_backups": 2,
		"max_age_days": 7
	},
	"Minecraft": {
		"server_dir": r'E:\..SERVERS\MINECRAFT\Minecraft server',
		"backup_dir": r'F:\GAMEBACKUPS\MINECRAFT',
		"max_backups": 2,
		"max_age_days": 7,
		"critical_files": {
			'world/': ['level.dat']
		}
	},
	"SCUM": {
		"server_dir": r"C:\Program Files (x86)\Steam\steamapps\common\SCUM Server\SCUM",
		"backup_dir": r"F:\GAMEBACKUPS\SCUM",
		"exclude_dirs": ["Content"],
		"max_backups": 2,
		"max_age_days": 7
	},
	"storage_warnings": {
		"space_gb": 50,
		"percent": 10
	}
}

def validate_backup_contents(backup_path, backup_type, critical_files=None):
	"""Validate backup integrity by checking critical files"""
	missing = []
	
	if backup_type == "world":
		worlds_path = os.path.join(backup_path, "worlds_local")
		if not os.path.exists(worlds_path):
			missing.append("Missing 'worlds_local' directory")
		else:
			world_files = [f for f in os.listdir(worlds_path) 
						   if f.endswith(('.fwl', '.db'))]
			if not world_files:
				missing.append("No world files (*.fwl, *.db) found")
	
	elif backup_type == "server":
		if critical_files:
			for critical_file in critical_files:
				file_path = os.path.join(backup_path, critical_file)
				if not os.path.exists(file_path):
					missing.append(f"Missing critical file: {critical_file}")
	
	return missing

@bot.command()
async def backupvalheim(ctx):
	"""Backup Valheim server and world with enhanced validation"""
	if not ctypes.windll.shell32.IsUserAnAdmin():
		await ctx.send("⚠️ Backup integrity checks limited without admin privileges!")
		return

	config = BACKUP_CONFIG["Valheim"]
	await run_combined_backup(
		ctx,
		"Valheim",
		config['server_dir'],
		config['world_dir'],
		config['backup_dir'],
		max_backups=config['max_backups']
	)

	latest = get_latest_valheim_backups(config['backup_dir'])
	for backup in latest:
		issues = validate_backup_contents(backup, "Valheim")
		if issues:
			await ctx.send(f"⚠️ Valheim backup issues:\n" + "\n".join(issues))

@bot.command()
async def backupdayz(ctx):
	"""Backup DayZ server with admin privilege check"""
	if not ctypes.windll.shell32.IsUserAnAdmin():
		await ctx.send("⚠️ Backup integrity checks limited without admin privileges!")
		return

	config = BACKUP_CONFIG["DayZ"]
	await run_backup(
		ctx,
		"DayZ",
		config['server_dir'],
		config['backup_dir'],
		exclude_dirs=config.get('exclude_dirs', []),
		max_backups=config['max_backups']
	)

@bot.command()
async def backupminecraft(ctx):
	"""Backup Minecraft server with admin privilege check"""
	if not ctypes.windll.shell32.IsUserAnAdmin():
		await ctx.send("⚠️ Backup integrity checks limited without admin privileges!")
		return

	config = BACKUP_CONFIG["Minecraft"]
	await run_backup(
		ctx,
		"Minecraft",
		config['server_dir'],
		config['backup_dir'],
		max_backups=config['max_backups']
	)

@bot.command()
async def backupscum(ctx):
	"""Backup SCUM server with admin privilege check"""
	if not ctypes.windll.shell32.IsUserAnAdmin():
		await ctx.send("⚠️ Backup integrity checks limited without admin privileges!")
		return

	config = BACKUP_CONFIG["SCUM"]
	await run_backup(
		ctx,
		"SCUM",
		config['server_dir'],
		config['backup_dir'],
		exclude_dirs=config.get('exclude_dirs', []),
		max_backups=config['max_backups']
	)
















# ============================================================================
# SERVER SHUTDOWN SYSTEM
# ============================================================================

def kill_minecraft_fabric_server():
	"""Terminate Minecraft (Fabric) server process by checking cmdline"""
	for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
		try:
			if "java.exe" in proc.info['name'].lower() and "fabric-server-launch" in ' '.join(proc.info['cmdline']).lower():
				proc.terminate()
				print("Terminated Minecraft (Fabric) server process.")
				break
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			continue

def stop_server_process(executable_name):
	"""Force terminate any server process by executable name"""
	for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
		try:
			if executable_name.lower() in proc.info['name'].lower():
				proc.terminate()
				print(f"Terminated {executable_name} server process.")
				break
		except (psutil.NoSuchProcess, psutil.AccessDenied):
			continue

def stop_scum_server_simple():
	"""Gracefully shutdown SCUM server using Ctrl+C for proper save"""
	executable_name = "SCUMServer.exe"
	
	try:
		print("Looking for SCUM server process...")
		
		scum_pid = None
		for proc in psutil.process_iter(['pid', 'name']):
			try:
				if proc.info['name'] and executable_name.lower() in proc.info['name'].lower():
					scum_pid = proc.info['pid']
					print(f"Found SCUM Server PID: {scum_pid}")
					break
			except (psutil.NoSuchProcess, psutil.AccessDenied):
				continue
		
		if not scum_pid:
			print("SCUM server not running")
			return True
		
		kernel32 = ctypes.windll.kernel32
		kernel32.FreeConsole()
		
		try:
			if kernel32.AttachConsole(scum_pid):
				print("Attached to console successfully")
				kernel32.SetConsoleCtrlHandler(None, True)
				
				if kernel32.GenerateConsoleCtrlEvent(0, 0):
					print("✓ Ctrl+C sent successfully!")
					time.sleep(10)
					kernel32.FreeConsole()
					kernel32.AttachConsole(-1)
					
					for i in range(20):
						try:
							psutil.Process(scum_pid)
							print(f"Waiting for save... {20-i} seconds remaining")
							time.sleep(1)
						except psutil.NoSuchProcess:
							print("✓ SCUM server saved and shut down gracefully!")
							return True
					
					print("⚠️ SCUM still running after timeout")
				else:
					print("✗ Failed to generate Ctrl+C event")
					kernel32.FreeConsole()
			else:
				print("✗ Could not attach to console (might not be a console app)")
		except Exception as e:
			print(f"✗ Console attachment failed: {e}")
		
		kernel32.AttachConsole(-1)
		print("\nForce killing SCUM server...")
		subprocess.run(["taskkill", "/IM", executable_name, "/F"], capture_output=True, timeout=10)
		return True
		
	except Exception as e:
		print(f"Error during shutdown: {e}")
		subprocess.run(["taskkill", "/IM", executable_name, "/F"])
		return True

@bot.command()
async def shutdownminecraft(ctx):
	"""Force shutdown Minecraft (Fabric) server with Discord embeds"""
	try:
		starting_embed = discord.Embed(
			title="🛑 Minecraft Server Shutdown",
			description="🚨 Initiating Minecraft (Fabric) server shutdown...",
			color=discord.Color.orange()
		)
		starting_embed.set_footer(text="This may take a moment...")
		message = await ctx.send(embed=starting_embed)
		
		kill_minecraft_fabric_server()
		
		success_embed = discord.Embed(
			title="✅ Minecraft Shutdown Complete",
			description="The Minecraft (Fabric) server has been successfully shut down.",
			color=discord.Color.green()
		)
		success_embed.set_footer(
			text=f"Requested by {ctx.author.display_name}",
			icon_url=ctx.author.avatar.url if ctx.author.avatar else None
		)
		
		await message.edit(embed=success_embed)
		
		backup_embed = discord.Embed(
			description=f"⚠️ **Backup Reminder**",
			color=discord.Color.blue()
		)
		backup_embed.set_thumbnail(url="https://i.imgur.com/MS1Tc3C.png")
		await ctx.send(embed=backup_embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Minecraft Shutdown Failed",
			description="An error occurred while shutting down the Minecraft server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Error Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server manually")
		await ctx.send(embed=error_embed)

@bot.command()
async def shutdownvalheim(ctx):
	"""Shutdown Valheim server with backup reminder"""
	try:
		starting_embed = discord.Embed(
			title="🛑 Valheim Server Shutdown",
			description="🚨 Initiating server shutdown process...",
			color=discord.Color.orange()
		)
		starting_embed.set_footer(text="Please wait...")
		message = await ctx.send(embed=starting_embed)
		
		stop_server_process("valheim_server.exe")
		
		success_embed = discord.Embed(
			title="✅ Valheim Server Shutdown Complete",
			description="The Valheim server has been successfully shut down.",
			color=discord.Color.green()
		)
		success_embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
		
		await message.edit(embed=success_embed)
		
		backup_embed = discord.Embed(
			description=f"⚠️ **Backup Reminder**",
			color=discord.Color.blue()
		)
		backup_embed.set_thumbnail(url="https://i.imgur.com/rkLRl6z.png")
		await ctx.send(embed=backup_embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Shutdown Failed",
			description=f"An error occurred while shutting down the Valheim server:\n```{e}```",
			color=discord.Color.red()
		)
		await ctx.send(embed=error_embed)

@bot.command()
async def shutdowndayz(ctx):
	"""Shutdown DayZ server with visual feedback"""
	try:
		starting_embed = discord.Embed(
			title="🛑 DayZ Server Shutdown",
			description="🚨 Initiating server shutdown process...",
			color=discord.Color.orange()
		)
		starting_embed.set_footer(text="Please wait...")
		message = await ctx.send(embed=starting_embed)
		
		stop_server_process("DayZServer_x64.exe")
		
		success_embed = discord.Embed(
			title="✅ DayZ Server Shutdown Complete",
			description="The DayZ server has been successfully shut down.",
			color=discord.Color.green()
		)
		success_embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
		
		await message.edit(embed=success_embed)
		
		backup_embed = discord.Embed(
			description=f" ⚠️ **Backup Reminder**",
			color=discord.Color.blue()
		)
		backup_embed.set_thumbnail(url="https://i.imgur.com/XbM95p1.jpeg")
		await ctx.send(embed=backup_embed)
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ Shutdown Failed",
			description="An error occurred while shutting down the DayZ server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Error Details", value=f"```{str(e)}```", inline=False)
		await ctx.send(embed=error_embed)

@bot.command()
async def shutdownscum(ctx):
	"""Graceful SCUM shutdown with Ctrl+C and auto-bot close after 20 seconds"""
	try:
		embed = discord.Embed(
			title="🛑 SCUM Server Shutdown",
			description="Initiating server shutdown...",
			color=discord.Color.orange()
		)
		embed.add_field(
			name="Process",
			value="1. Graceful termination signal\n2. Force kill (if needed)",
			inline=False
		)
		message = await ctx.send(embed=embed)
		
		if stop_scum_server_simple():
			success_embed = discord.Embed(
				title="✅ SCUM Server Shutdown Complete",
				description="Server has been shut down successfully. Please wait 1 minute before using backup command",
				color=discord.Color.green()
			)
		else:
			success_embed = discord.Embed(
				title="⚠️ SCUM Server Status Unknown",
				description="Shutdown command was sent. Please verify manually.",
				color=discord.Color.yellow()
			)
		
		success_embed.set_footer(
			text=f"Requested by {ctx.author.display_name}",
			icon_url=ctx.author.avatar.url if ctx.author.avatar else None
		)
		
		await message.edit(embed=success_embed)
		
		if "✅" in success_embed.title:
			backup_embed = discord.Embed(
				description="💾 **Backup Reminder:** Server is stopped - perfect time for backups!",
				color=discord.Color.blue()
			)
			await ctx.send(embed=backup_embed)
		
		await asyncio.sleep(20)
		await ctx.bot.close()
	
	except Exception as e:
		error_embed = discord.Embed(
			title="❌ SCUM Shutdown Failed",
			description="An error occurred while shutting down the SCUM server:",
			color=discord.Color.red()
		)
		error_embed.add_field(name="Error Details", value=f"```{str(e)}```", inline=False)
		error_embed.set_footer(text="Please check the server manually")
		await ctx.send(embed=error_embed)


	


# Run the bot with your token
bot.run(DISCORD_TOKEN)

print("Press ESC to close or Enter to exit...")
