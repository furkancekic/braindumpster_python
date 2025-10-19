"""
Localization Service for Backend-Driven Multi-Language Support

This service handles:
- Date formatting in different languages
- Priority translations
- Relative time formatting ("Today", "Tomorrow", etc.)
- Text localization for task-related content
"""

from datetime import datetime, timedelta, date
from typing import Dict, Optional, Any
import logging


class LocalizationService:
    """Service for handling backend localization"""
    
    def __init__(self):
        self.logger = logging.getLogger('braindumpster.localization')
        self.logger.info("🌍 Initializing LocalizationService...")
        
        # Supported languages
        self.supported_languages = ["en", "tr", "de", "fr", "es", "ar"]
        self.default_language = "en"
        
        # Initialize translations
        self._init_translations()
        
        self.logger.info(f"✅ LocalizationService initialized with {len(self.supported_languages)} languages")
    
    def _init_translations(self):
        """Initialize translation dictionaries for all supported languages"""
        
        # Priority translations
        self.priority_translations = {
            "en": {
                "low": "Low",
                "medium": "Medium", 
                "high": "High",
                "urgent": "Urgent"
            },
            "tr": {
                "low": "Düşük",
                "medium": "Orta",
                "high": "Yüksek", 
                "urgent": "Acil"
            },
            "de": {
                "low": "Niedrig",
                "medium": "Mittel",
                "high": "Hoch",
                "urgent": "Dringend"
            },
            "fr": {
                "low": "Faible",
                "medium": "Moyen",
                "high": "Élevé",
                "urgent": "Urgent"
            },
            "es": {
                "low": "Bajo",
                "medium": "Medio",
                "high": "Alto",
                "urgent": "Urgente"
            },
            "ar": {
                "low": "منخفض",
                "medium": "متوسط",
                "high": "عالي",
                "urgent": "عاجل"
            }
        }
        
        # Relative time translations
        self.time_translations = {
            "en": {
                "today": "Today",
                "tomorrow": "Tomorrow",
                "yesterday": "Yesterday",
                "days_ago": "{} days ago",
                "day_ago": "{} day ago",
                "days_overdue": "{} days overdue",
                "day_overdue": "{} day overdue",
                "in_days": "in {} days",
                "in_day": "in {} day",
                "minutes_ago": "{}m ago",
                "hours_ago": "{}h ago",
                "in_minutes": "in {}m",
                "in_hours": "in {}h {}m",
                "at_time": "at {}",
                "reminders": "Reminders",
                "more": "more"
            },
            "tr": {
                "today": "Bugün",
                "tomorrow": "Yarın",
                "yesterday": "Dün",
                "days_ago": "{} gün önce",
                "day_ago": "{} gün önce",
                "days_overdue": "{} gün gecikmiş",
                "day_overdue": "{} gün gecikmiş", 
                "in_days": "{} gün sonra",
                "in_day": "{} gün sonra",
                "minutes_ago": "{}d önce",
                "hours_ago": "{}s önce",
                "in_minutes": "{}d sonra",
                "in_hours": "{}s {}d sonra",
                "at_time": "saat {}",
                "reminders": "Hatırlatıcılar",
                "more": "daha fazla"
            },
            "de": {
                "today": "Heute",
                "tomorrow": "Morgen",
                "yesterday": "Gestern",
                "days_ago": "vor {} Tagen",
                "day_ago": "vor {} Tag",
                "days_overdue": "{} Tage überfällig",
                "day_overdue": "{} Tag überfällig",
                "in_days": "in {} Tagen",
                "in_day": "in {} Tag",
                "minutes_ago": "vor {}m",
                "hours_ago": "vor {}h",
                "in_minutes": "in {}m",
                "in_hours": "in {}h {}m",
                "at_time": "um {}",
                "reminders": "Erinnerungen",
                "more": "weitere"
            },
            "fr": {
                "today": "Aujourd'hui",
                "tomorrow": "Demain",
                "yesterday": "Hier",
                "days_ago": "il y a {} jours",
                "day_ago": "il y a {} jour",
                "days_overdue": "{} jours en retard",
                "day_overdue": "{} jour en retard",
                "in_days": "dans {} jours",
                "in_day": "dans {} jour",
                "minutes_ago": "il y a {}m",
                "hours_ago": "il y a {}h",
                "in_minutes": "dans {}m",
                "in_hours": "dans {}h {}m",
                "at_time": "à {}",
                "reminders": "Rappels",
                "more": "de plus"
            },
            "es": {
                "today": "Hoy",
                "tomorrow": "Mañana",
                "yesterday": "Ayer",
                "days_ago": "hace {} días",
                "day_ago": "hace {} día",
                "days_overdue": "{} días de retraso",
                "day_overdue": "{} día de retraso",
                "in_days": "en {} días",
                "in_day": "en {} día",
                "minutes_ago": "hace {}m",
                "hours_ago": "hace {}h",
                "in_minutes": "en {}m",
                "in_hours": "en {}h {}m",
                "at_time": "a las {}",
                "reminders": "Recordatorios",
                "more": "más"
            },
            "ar": {
                "today": "اليوم",
                "tomorrow": "غداً",
                "yesterday": "أمس",
                "days_ago": "منذ {} أيام",
                "day_ago": "منذ {} يوم",
                "days_overdue": "متأخر {} أيام",
                "day_overdue": "متأخر {} يوم",
                "in_days": "خلال {} أيام",
                "in_day": "خلال {} يوم",
                "minutes_ago": "منذ {}د",
                "hours_ago": "منذ {}س",
                "in_minutes": "خلال {}د",
                "in_hours": "خلال {}س {}د",
                "at_time": "في {}",
                "reminders": "التذكيرات",
                "more": "المزيد"
            }
        }
        
        # Month names for date formatting
        self.month_names = {
            "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            "tr": ["Oca", "Şub", "Mar", "Nis", "May", "Haz",
                   "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"],
            "de": ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"],
            "fr": ["Jan", "Fév", "Mar", "Avr", "Mai", "Jun",
                   "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"],
            "es": ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                   "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"],
            "ar": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                   "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        }
    
    def get_supported_languages(self) -> list:
        """Get list of supported language codes"""
        return self.supported_languages.copy()
    
    def is_language_supported(self, language_code: str) -> bool:
        """Check if a language is supported"""
        return language_code.lower() in self.supported_languages
    
    def validate_language(self, language_code: str) -> str:
        """Validate and return a supported language code"""
        if not language_code or not isinstance(language_code, str):
            return self.default_language
            
        lang = language_code.lower().strip()
        return lang if self.is_language_supported(lang) else self.default_language
    
    def get_priority_translation(self, priority: str, language: str = "en") -> str:
        """Get localized priority name"""
        language = self.validate_language(language)
        
        if priority not in ["low", "medium", "high", "urgent"]:
            priority = "medium"  # Default fallback
            
        try:
            return self.priority_translations[language][priority]
        except KeyError:
            self.logger.warning(f"⚠️ Priority translation not found: {priority} in {language}")
            return self.priority_translations[self.default_language][priority]
    
    def format_due_date(self, due_date: datetime, language: str = "en") -> str:
        """Format due date with relative time in user's language"""
        language = self.validate_language(language)
        
        try:
            now = datetime.now()
            today = date.today()
            due_date_only = due_date.date() if isinstance(due_date, datetime) else due_date
            
            # Calculate difference
            diff = (due_date_only - today).days
            
            # Get translations for this language
            t = self.time_translations[language]
            
            if diff == 0:
                return t["today"]
            elif diff == 1:
                return t["tomorrow"]
            elif diff == -1:
                return t["yesterday"]
            elif diff < 0:
                abs_diff = abs(diff)
                if abs_diff == 1:
                    return t["day_overdue"].format(abs_diff)
                else:
                    return t["days_overdue"].format(abs_diff)
            elif diff <= 7:
                if diff == 1:
                    return t["in_day"].format(diff)
                else:
                    return t["in_days"].format(diff)
            else:
                # Use month abbreviation for dates further away
                month_names = self.month_names[language]
                month_name = month_names[due_date.month - 1]
                return f"{month_name} {due_date.day}"
                
        except Exception as e:
            self.logger.error(f"❌ Error formatting due date: {e}")
            # Fallback to English
            return self.format_due_date(due_date, "en")
    
    def format_reminder_time(self, reminder_time: datetime, language: str = "en") -> str:
        """Format reminder time with relative time in user's language"""
        language = self.validate_language(language)
        
        try:
            now = datetime.now()
            today = date.today()
            reminder_date = reminder_time.date()
            tomorrow = today + timedelta(days=1)
            
            # Get translations for this language
            t = self.time_translations[language]
            
            # Format time
            time_format = reminder_time.strftime("%H:%M")
            
            if reminder_date == today:
                if reminder_time < now:
                    diff = now - reminder_time
                    if diff.total_seconds() < 3600:  # Less than 1 hour
                        minutes = int(diff.total_seconds() // 60)
                        return t["minutes_ago"].format(minutes)
                    else:
                        hours = int(diff.total_seconds() // 3600)
                        return t["hours_ago"].format(hours)
                else:
                    diff = reminder_time - now
                    if diff.total_seconds() < 3600:  # Less than 1 hour
                        minutes = int(diff.total_seconds() // 60)
                        return t["in_minutes"].format(minutes)
                    elif diff.total_seconds() < 7200:  # Less than 2 hours
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)
                        return t["in_hours"].format(hours, minutes)
                    else:
                        return f"{t['today']} {t['at_time'].format(time_format)}"
            elif reminder_date == tomorrow:
                return f"{t['tomorrow']} {t['at_time'].format(time_format)}"
            elif reminder_time.year == now.year:
                month_names = self.month_names[language]
                month_name = month_names[reminder_time.month - 1]
                return f"{month_name} {reminder_time.day}, {time_format}"
            else:
                month_names = self.month_names[language]
                month_name = month_names[reminder_time.month - 1]
                return f"{month_name} {reminder_time.day} {reminder_time.year}, {time_format}"
                
        except Exception as e:
            self.logger.error(f"❌ Error formatting reminder time: {e}")
            # Fallback to English
            return self.format_reminder_time(reminder_time, "en")
    
    def localize_task_data(self, task_data: Dict, language: str = "en") -> Dict:
        """Localize task data with formatted dates and priorities"""
        language = self.validate_language(language)
        
        try:
            # Create a copy to avoid modifying original
            localized_task = task_data.copy()
            
            # Add localized priority
            if "priority" in task_data:
                localized_task["priority_localized"] = self.get_priority_translation(
                    task_data["priority"], language
                )
            
            # Add localized due date
            if "due_date" in task_data and task_data["due_date"]:
                due_date = task_data["due_date"]
                if isinstance(due_date, str):
                    due_date = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                
                localized_task["due_date_localized"] = self.format_due_date(due_date, language)
            
            # Add localized reminders
            if "reminders" in task_data and task_data["reminders"]:
                localized_reminders = []
                for reminder in task_data["reminders"]:
                    localized_reminder = reminder.copy()
                    
                    if "reminder_time" in reminder and reminder["reminder_time"]:
                        reminder_time = reminder["reminder_time"]
                        if isinstance(reminder_time, str):
                            reminder_time = datetime.fromisoformat(reminder_time.replace('Z', '+00:00'))
                        
                        localized_reminder["reminder_time_localized"] = self.format_reminder_time(
                            reminder_time, language
                        )
                    
                    localized_reminders.append(localized_reminder)
                
                localized_task["reminders_localized"] = localized_reminders
            
            # Add language info
            localized_task["language"] = language
            
            return localized_task
            
        except Exception as e:
            self.logger.error(f"❌ Error localizing task data: {e}")
            # Return original data with language info
            task_data["language"] = language
            return task_data
    
    def get_text_translation(self, key: str, language: str = "en") -> str:
        """Get text translation for a given key"""
        language = self.validate_language(language)
        
        try:
            return self.time_translations[language].get(key, key)
        except KeyError:
            return self.time_translations[self.default_language].get(key, key)
    
    def localize_task_list(self, tasks: list, language: str = "en") -> list:
        """Localize a list of tasks"""
        language = self.validate_language(language)
        
        try:
            localized_tasks = []
            for task in tasks:
                localized_task = self.localize_task_data(task, language)
                localized_tasks.append(localized_task)
            
            self.logger.debug(f"🌍 Localized {len(tasks)} tasks for language: {language}")
            return localized_tasks
            
        except Exception as e:
            self.logger.error(f"❌ Error localizing task list: {e}")
            return tasks  # Return original tasks on error
    
    def get_reminder_summary(self, reminder_count: int, language: str = "en") -> str:
        """Get localized reminder summary text"""
        language = self.validate_language(language)
        
        try:
            t = self.time_translations[language]
            if reminder_count > 3:
                return f"+{reminder_count - 3} {t['more']}"
            else:
                return f"{t['reminders']} ({reminder_count})"
        except Exception as e:
            self.logger.error(f"❌ Error getting reminder summary: {e}")
            return f"Reminders ({reminder_count})"  # English fallback