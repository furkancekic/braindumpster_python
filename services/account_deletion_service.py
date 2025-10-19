import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import requests
import os

from services.firebase_service import FirebaseService
from models.deletion_request import DeletionRequest

class AccountDeletionService:
    def __init__(self, firebase_service: FirebaseService):
        self.firebase_service = firebase_service
        self.logger = logging.getLogger('braindumpster.deletion_service')
        self.deletion_steps = [
            self._delete_user_tasks,
            self._delete_conversation_history,
            self._delete_voice_recordings,
            self._delete_user_preferences,
            self._delete_notification_tokens,
            self._cleanup_revenuecat_data,
            self._cleanup_firebase_analytics,
            self._delete_firebase_user,
            self._cleanup_third_party_services,
            self._finalize_deletion
        ]

    async def process_account_deletion(
        self,
        user_id: str,
        request_id: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Process complete account deletion
        """
        self.logger.info(f"🗑️ Starting account deletion process for user: {user_id}")

        deletion_report = {
            "user_id": user_id,
            "request_id": request_id,
            "started_at": datetime.utcnow().isoformat(),
            "steps_completed": [],
            "steps_failed": [],
            "total_items_deleted": 0,
            "status": "processing"
        }

        try:
            # Update deletion request status to processing
            self._update_deletion_status(request_id, "processing")

            # Execute deletion steps
            for step_func in self.deletion_steps:
                step_name = step_func.__name__
                self.logger.info(f"🔄 Executing deletion step: {step_name}")

                try:
                    step_result = await step_func(user_id)
                    deletion_report["steps_completed"].append({
                        "step": step_name,
                        "completed_at": datetime.utcnow().isoformat(),
                        "items_deleted": step_result.get("items_deleted", 0),
                        "details": step_result.get("details", {})
                    })
                    deletion_report["total_items_deleted"] += step_result.get("items_deleted", 0)

                    self.logger.info(f"✅ Step completed: {step_name}")

                except Exception as e:
                    self.logger.error(f"❌ Step failed: {step_name} - {e}")
                    deletion_report["steps_failed"].append({
                        "step": step_name,
                        "failed_at": datetime.utcnow().isoformat(),
                        "error": str(e)
                    })

            # Determine final status
            if len(deletion_report["steps_failed"]) == 0:
                deletion_report["status"] = "completed"
                self._update_deletion_status(request_id, "completed")
            else:
                deletion_report["status"] = "partially_completed"
                self._update_deletion_status(request_id, "failed",
                    f"Some deletion steps failed: {len(deletion_report['steps_failed'])} failures")

            deletion_report["completed_at"] = datetime.utcnow().isoformat()

            self.logger.info(f"🏁 Account deletion process completed for user: {user_id}")
            self.logger.info(f"📊 Deletion summary: {deletion_report['total_items_deleted']} items deleted, "
                           f"{len(deletion_report['steps_completed'])} steps completed, "
                           f"{len(deletion_report['steps_failed'])} steps failed")

            return deletion_report

        except Exception as e:
            self.logger.error(f"💥 Critical error in account deletion process: {e}")
            deletion_report["status"] = "failed"
            deletion_report["error"] = str(e)
            deletion_report["completed_at"] = datetime.utcnow().isoformat()

            self._update_deletion_status(request_id, "failed", str(e))

            return deletion_report

    async def _delete_user_tasks(self, user_id: str) -> Dict[str, Any]:
        """Delete all user tasks and subtasks"""
        self.logger.info(f"🗂️ Deleting user tasks for: {user_id}")

        items_deleted = 0

        try:
            if self.firebase_service.db:
                # Delete tasks
                tasks_query = self.firebase_service.db.collection('tasks')\
                    .where('user_id', '==', user_id)

                tasks = tasks_query.stream()
                for task in tasks:
                    task.reference.delete()
                    items_deleted += 1

                # Delete subtasks
                subtasks_query = self.firebase_service.db.collection('subtasks')\
                    .where('user_id', '==', user_id)

                subtasks = subtasks_query.stream()
                for subtask in subtasks:
                    subtask.reference.delete()
                    items_deleted += 1

            return {
                "items_deleted": items_deleted,
                "details": {"tasks_and_subtasks": items_deleted}
            }

        except Exception as e:
            self.logger.error(f"Error deleting user tasks: {e}")
            raise

    async def _delete_conversation_history(self, user_id: str) -> Dict[str, Any]:
        """Delete all conversation history and AI interactions"""
        self.logger.info(f"💬 Deleting conversation history for: {user_id}")

        items_deleted = 0

        try:
            if self.firebase_service.db:
                # Delete conversations
                conversations_query = self.firebase_service.db.collection('conversations')\
                    .where('user_id', '==', user_id)

                conversations = conversations_query.stream()
                for conversation in conversations:
                    conversation.reference.delete()
                    items_deleted += 1

                # Delete chat messages
                messages_query = self.firebase_service.db.collection('chat_messages')\
                    .where('user_id', '==', user_id)

                messages = messages_query.stream()
                for message in messages:
                    message.reference.delete()
                    items_deleted += 1

            return {
                "items_deleted": items_deleted,
                "details": {"conversations_and_messages": items_deleted}
            }

        except Exception as e:
            self.logger.error(f"Error deleting conversation history: {e}")
            raise

    async def _delete_voice_recordings(self, user_id: str) -> Dict[str, Any]:
        """Delete all voice recordings and transcriptions"""
        self.logger.info(f"🎤 Deleting voice recordings for: {user_id}")

        items_deleted = 0

        try:
            # Delete local voice recordings
            voice_recordings_path = f"voice_recordings/{user_id}"
            if os.path.exists(voice_recordings_path):
                import shutil
                shutil.rmtree(voice_recordings_path)
                items_deleted += 1

            # Delete voice recording metadata from Firebase
            if self.firebase_service.db:
                recordings_query = self.firebase_service.db.collection('voice_recordings')\
                    .where('user_id', '==', user_id)

                recordings = recordings_query.stream()
                for recording in recordings:
                    recording.reference.delete()
                    items_deleted += 1

            # TODO(context7): Delete from cloud storage if using GCS/S3
            # await self._delete_cloud_storage_files(user_id)

            return {
                "items_deleted": items_deleted,
                "details": {"voice_recordings": items_deleted}
            }

        except Exception as e:
            self.logger.error(f"Error deleting voice recordings: {e}")
            raise

    async def _delete_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """Delete user preferences and settings"""
        self.logger.info(f"⚙️ Deleting user preferences for: {user_id}")

        items_deleted = 0

        try:
            if self.firebase_service.db:
                # Delete user preferences
                prefs_doc = self.firebase_service.db.collection('user_preferences')\
                    .document(user_id)

                if prefs_doc.get().exists:
                    prefs_doc.delete()
                    items_deleted += 1

                # Delete user settings
                settings_doc = self.firebase_service.db.collection('user_settings')\
                    .document(user_id)

                if settings_doc.get().exists:
                    settings_doc.delete()
                    items_deleted += 1

            return {
                "items_deleted": items_deleted,
                "details": {"preferences_and_settings": items_deleted}
            }

        except Exception as e:
            self.logger.error(f"Error deleting user preferences: {e}")
            raise

    async def _delete_notification_tokens(self, user_id: str) -> Dict[str, Any]:
        """Delete notification tokens and preferences"""
        self.logger.info(f"🔔 Deleting notification tokens for: {user_id}")

        items_deleted = 0

        try:
            if self.firebase_service.db:
                # Delete notification tokens
                tokens_query = self.firebase_service.db.collection('notification_tokens')\
                    .where('user_id', '==', user_id)

                tokens = tokens_query.stream()
                for token in tokens:
                    token.reference.delete()
                    items_deleted += 1

                # Delete notification history
                history_query = self.firebase_service.db.collection('notification_history')\
                    .where('user_id', '==', user_id)

                history = history_query.stream()
                for notification in history:
                    notification.reference.delete()
                    items_deleted += 1

            return {
                "items_deleted": items_deleted,
                "details": {"notification_data": items_deleted}
            }

        except Exception as e:
            self.logger.error(f"Error deleting notification tokens: {e}")
            raise

    async def _cleanup_revenuecat_data(self, user_id: str) -> Dict[str, Any]:
        """Request RevenueCat data deletion"""
        self.logger.info(f"💳 Cleaning up RevenueCat data for: {user_id}")

        try:
            import aiohttp
            import os

            # Get RevenueCat API key from environment
            revenuecat_api_key = os.environ.get('REVENUECAT_SECRET_API_KEY')

            if not revenuecat_api_key:
                self.logger.warning("RevenueCat API key not configured, skipping deletion")
                return {
                    "items_deleted": 0,
                    "details": {"revenuecat_skipped": "API key not configured"}
                }

            # RevenueCat GDPR Deletion API
            headers = {
                'Authorization': f'Bearer {revenuecat_api_key}',
                'Content-Type': 'application/json'
            }

            url = f'https://api.revenuecat.com/v1/subscribers/{user_id}'

            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers) as response:
                    if response.status in [200, 204, 404]:
                        # 200/204: Successfully deleted
                        # 404: User not found (already deleted or never existed)
                        self.logger.info(f"✅ RevenueCat data deletion completed for user: {user_id}")
                        return {
                            "items_deleted": 1,
                            "details": {
                                "revenuecat_user_deleted": True,
                                "status_code": response.status
                            }
                        }
                    else:
                        error_text = await response.text()
                        self.logger.error(f"RevenueCat deletion failed: {response.status} - {error_text}")
                        return {
                            "items_deleted": 0,
                            "details": {"revenuecat_error": f"API error: {response.status}"}
                        }

        except Exception as e:
            self.logger.error(f"Error cleaning up RevenueCat data: {e}")
            # Don't fail the entire deletion process for third-party service failures
            return {
                "items_deleted": 0,
                "details": {"revenuecat_error": str(e)}
            }

    async def _cleanup_firebase_analytics(self, user_id: str) -> Dict[str, Any]:
        """Request Firebase Analytics data deletion"""
        self.logger.info(f"📊 Cleaning up Firebase Analytics data for: {user_id}")

        try:
            import aiohttp
            import os
            from google.oauth2.service_account import Credentials
            import json

            # Get Firebase project ID
            firebase_project_id = os.environ.get('FIREBASE_PROJECT_ID')
            if not firebase_project_id:
                self.logger.warning("Firebase project ID not configured, skipping Analytics deletion")
                return {
                    "items_deleted": 0,
                    "details": {"analytics_skipped": "Project ID not configured"}
                }

            # Try to get service account credentials
            try:
                service_account_key = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
                if service_account_key and os.path.exists(service_account_key):
                    # Use Google Analytics Data Deletion API
                    # This requires proper service account setup with Analytics API access

                    credentials = Credentials.from_service_account_file(
                        service_account_key,
                        scopes=['https://www.googleapis.com/auth/analytics.user.deletion']
                    )

                    # Get access token
                    from google.auth.transport.requests import Request
                    credentials.refresh(Request())
                    access_token = credentials.token

                    # Firebase Analytics deletion endpoint
                    headers = {
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json'
                    }

                    # Create user deletion request
                    deletion_request = {
                        'userId': user_id,
                        'kind': 'analytics#userDeletionRequest'
                    }

                    url = f'https://analyticsreporting.googleapis.com/v4/userDeletion:upsert'

                    async with aiohttp.ClientSession() as session:
                        async with session.post(url, headers=headers, json=deletion_request) as response:
                            if response.status in [200, 201]:
                                response_data = await response.json()
                                self.logger.info(f"✅ Firebase Analytics deletion request submitted for user: {user_id}")
                                return {
                                    "items_deleted": 1,
                                    "details": {
                                        "analytics_deletion_requested": True,
                                        "request_id": response_data.get('id', 'unknown'),
                                        "status_code": response.status
                                    }
                                }
                            else:
                                error_text = await response.text()
                                self.logger.error(f"Analytics deletion failed: {response.status} - {error_text}")
                                return {
                                    "items_deleted": 0,
                                    "details": {"analytics_error": f"API error: {response.status}"}
                                }

                else:
                    self.logger.warning("Google service account credentials not found, logging deletion requirement")
                    return {
                        "items_deleted": 0,
                        "details": {"analytics_skipped": "Service account not configured"}
                    }

            except ImportError:
                self.logger.warning("Google Auth library not available, skipping Analytics deletion")
                return {
                    "items_deleted": 0,
                    "details": {"analytics_skipped": "Google Auth library not available"}
                }

        except Exception as e:
            self.logger.error(f"Error cleaning up Firebase Analytics: {e}")
            # Don't fail the entire deletion process for third-party service failures
            return {
                "items_deleted": 0,
                "details": {"analytics_error": str(e)}
            }

    async def _delete_firebase_user(self, user_id: str) -> Dict[str, Any]:
        """Delete Firebase Auth user"""
        self.logger.info(f"👤 Deleting Firebase Auth user: {user_id}")

        try:
            # Delete user from Firebase Auth
            from firebase_admin import auth
            auth.delete_user(user_id)

            # Delete user document from Firestore
            if self.firebase_service.db:
                user_doc = self.firebase_service.db.collection('users').document(user_id)
                if user_doc.get().exists:
                    user_doc.delete()

            return {
                "items_deleted": 1,
                "details": {"firebase_user_deleted": True}
            }

        except Exception as e:
            self.logger.error(f"Error deleting Firebase user: {e}")
            raise

    async def _cleanup_third_party_services(self, user_id: str) -> Dict[str, Any]:
        """Cleanup data from other third-party services"""
        self.logger.info(f"🌐 Cleaning up third-party services for: {user_id}")

        cleanup_results = []

        try:
            # TODO(context7): Add other third-party service cleanups as needed
            # Examples:
            # - Analytics services (Mixpanel, Amplitude, etc.)
            # - Customer support tools (Intercom, Zendesk, etc.)
            # - Email marketing services (Mailchimp, SendGrid, etc.)
            # - Crash reporting services (Crashlytics, Sentry, etc.)

            self.logger.info(f"📝 Third-party cleanup completed for user: {user_id}")

            return {
                "items_deleted": len(cleanup_results),
                "details": {"third_party_cleanups": cleanup_results}
            }

        except Exception as e:
            self.logger.error(f"Error cleaning up third-party services: {e}")
            raise

    async def _finalize_deletion(self, user_id: str) -> Dict[str, Any]:
        """Finalize deletion process and cleanup any remaining references"""
        self.logger.info(f"🏁 Finalizing deletion for: {user_id}")

        try:
            # Final cleanup of any remaining user references
            if self.firebase_service.db:
                # Delete any remaining documents that reference this user
                collections_to_check = ['user_sessions', 'audit_logs', 'feedback']

                items_cleaned = 0
                for collection_name in collections_to_check:
                    try:
                        docs = self.firebase_service.db.collection(collection_name)\
                            .where('user_id', '==', user_id).stream()

                        for doc in docs:
                            doc.reference.delete()
                            items_cleaned += 1
                    except Exception as e:
                        self.logger.warning(f"Could not clean collection {collection_name}: {e}")

            self.logger.info(f"✅ Deletion finalized for user: {user_id}")

            return {
                "items_deleted": items_cleaned,
                "details": {"final_cleanup_items": items_cleaned}
            }

        except Exception as e:
            self.logger.error(f"Error finalizing deletion: {e}")
            raise

    def export_user_data(self, user_id: str, export_format: str = 'json') -> Dict[str, Any]:
        """
        Export all user data in the specified format

        Args:
            user_id: The user ID to export data for
            export_format: The format to export in (json, csv, xml, ics)

        Returns:
            Dict containing the exported data
        """
        self.logger.info(f"📤 Starting data export for user: {user_id}, format: {export_format}")

        try:
            export_data = {
                "export_metadata": {
                    "user_id": user_id,
                    "export_date": datetime.utcnow().isoformat(),
                    "format": export_format,
                    "version": "1.0"
                },
                "user_data": {}
            }

            # Export user profile and preferences
            user_data = self._export_user_profile(user_id)
            if user_data:
                export_data["user_data"]["profile"] = user_data

            # Export tasks
            tasks_data = self._export_user_tasks(user_id)
            if tasks_data:
                export_data["user_data"]["tasks"] = tasks_data

            # Export conversations
            conversations_data = self._export_user_conversations(user_id)
            if conversations_data:
                export_data["user_data"]["conversations"] = conversations_data

            # Export voice recordings metadata (not the actual files for privacy)
            voice_data = self._export_voice_recordings_metadata(user_id)
            if voice_data:
                export_data["user_data"]["voice_recordings"] = voice_data

            # Export subscription data
            subscription_data = self._export_subscription_data(user_id)
            if subscription_data:
                export_data["user_data"]["subscriptions"] = subscription_data

            # Format the data according to the requested format
            if export_format == 'json':
                return export_data
            elif export_format == 'csv':
                return self._format_as_csv(export_data)
            elif export_format == 'xml':
                return self._format_as_xml(export_data)
            elif export_format == 'ics':
                return self._format_as_ics(export_data)
            else:
                raise ValueError(f"Unsupported export format: {export_format}")

        except Exception as e:
            self.logger.error(f"❌ Error exporting user data: {e}")
            raise

    def _export_user_profile(self, user_id: str) -> Dict[str, Any]:
        """Export user profile and preferences"""
        profile_data = {}

        try:
            if self.firebase_service.db:
                # Get user profile
                user_doc = self.firebase_service.db.collection('users').document(user_id).get()
                if user_doc.exists:
                    profile_data['profile'] = user_doc.to_dict()

                # Get user preferences
                prefs_doc = self.firebase_service.db.collection('user_preferences').document(user_id).get()
                if prefs_doc.exists:
                    profile_data['preferences'] = prefs_doc.to_dict()

            return profile_data
        except Exception as e:
            self.logger.warning(f"Could not export user profile: {e}")
            return {}

    def _export_user_tasks(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user tasks"""
        tasks_data = []

        try:
            if self.firebase_service.db:
                tasks = self.firebase_service.db.collection('tasks')\
                    .where('user_id', '==', user_id).stream()

                for task in tasks:
                    task_data = task.to_dict()
                    task_data['id'] = task.id
                    tasks_data.append(task_data)

            return tasks_data
        except Exception as e:
            self.logger.warning(f"Could not export user tasks: {e}")
            return []

    def _export_user_conversations(self, user_id: str) -> List[Dict[str, Any]]:
        """Export user conversations"""
        conversations_data = []

        try:
            if self.firebase_service.db:
                conversations = self.firebase_service.db.collection('conversations')\
                    .where('user_id', '==', user_id).stream()

                for conversation in conversations:
                    conv_data = conversation.to_dict()
                    conv_data['id'] = conversation.id
                    conversations_data.append(conv_data)

            return conversations_data
        except Exception as e:
            self.logger.warning(f"Could not export user conversations: {e}")
            return []

    def _export_voice_recordings_metadata(self, user_id: str) -> List[Dict[str, Any]]:
        """Export voice recordings metadata (not actual files)"""
        voice_data = []

        try:
            # Export metadata only for privacy reasons
            import os
            user_voice_dir = f"voice_recordings/{user_id}"

            if os.path.exists(user_voice_dir):
                for root, dirs, files in os.walk(user_voice_dir):
                    for file in files:
                        if file.endswith('.wav'):
                            file_path = os.path.join(root, file)
                            file_stats = os.stat(file_path)
                            voice_data.append({
                                "filename": file,
                                "created_date": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                                "size_bytes": file_stats.st_size,
                                "relative_path": os.path.relpath(file_path, user_voice_dir)
                            })

            return voice_data
        except Exception as e:
            self.logger.warning(f"Could not export voice recordings metadata: {e}")
            return []

    def _export_subscription_data(self, user_id: str) -> Dict[str, Any]:
        """Export subscription and billing data"""
        subscription_data = {}

        try:
            if self.firebase_service.db:
                # Get subscription data
                sub_doc = self.firebase_service.db.collection('subscriptions').document(user_id).get()
                if sub_doc.exists:
                    subscription_data = sub_doc.to_dict()

            return subscription_data
        except Exception as e:
            self.logger.warning(f"Could not export subscription data: {e}")
            return {}

    def _format_as_csv(self, data: Dict[str, Any]) -> str:
        """Format export data as CSV"""
        import csv
        import io

        output = io.StringIO()

        # Write metadata
        writer = csv.writer(output)
        writer.writerow(['Export Metadata'])
        for key, value in data['export_metadata'].items():
            writer.writerow([key, value])

        writer.writerow([])  # Empty row

        # Write user profile
        if 'profile' in data['user_data']:
            writer.writerow(['User Profile'])
            profile = data['user_data']['profile']
            for key, value in profile.items():
                writer.writerow([key, str(value)])

        # Write tasks
        if 'tasks' in data['user_data']:
            writer.writerow([])
            writer.writerow(['Tasks'])
            tasks = data['user_data']['tasks']
            if tasks:
                # Write header
                headers = ['id'] + list(tasks[0].keys() - {'id'})
                writer.writerow(headers)

                # Write task data
                for task in tasks:
                    row = [task.get(header, '') for header in headers]
                    writer.writerow(row)

        return output.getvalue()

    def _format_as_xml(self, data: Dict[str, Any]) -> str:
        """Format export data as XML"""
        import xml.etree.ElementTree as ET

        root = ET.Element("user_data_export")

        # Add metadata
        metadata = ET.SubElement(root, "metadata")
        for key, value in data['export_metadata'].items():
            elem = ET.SubElement(metadata, key)
            elem.text = str(value)

        # Add user data
        user_data = ET.SubElement(root, "user_data")

        for section, section_data in data['user_data'].items():
            section_elem = ET.SubElement(user_data, section)

            if isinstance(section_data, list):
                for item in section_data:
                    item_elem = ET.SubElement(section_elem, "item")
                    for key, value in item.items():
                        elem = ET.SubElement(item_elem, key)
                        elem.text = str(value)
            elif isinstance(section_data, dict):
                for key, value in section_data.items():
                    elem = ET.SubElement(section_elem, key)
                    elem.text = str(value)

        return ET.tostring(root, encoding='unicode')

    def _format_as_ics(self, data: Dict[str, Any]) -> str:
        """Format tasks as ICS calendar file"""
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Brain Dumpster//User Data Export//EN",
            "CALSCALE:GREGORIAN"
        ]

        # Convert tasks to calendar events
        if 'tasks' in data['user_data']:
            for task in data['user_data']['tasks']:
                if task.get('due_date'):
                    ics_lines.extend([
                        "BEGIN:VEVENT",
                        f"UID:{task.get('id', 'unknown')}@braindumpster.app",
                        f"SUMMARY:{task.get('title', 'Untitled Task')}",
                        f"DESCRIPTION:{task.get('description', '')}",
                        f"DTSTART:{self._format_date_for_ics(task.get('due_date'))}",
                        f"DTEND:{self._format_date_for_ics(task.get('due_date'))}",
                        f"CREATED:{self._format_date_for_ics(task.get('created_at'))}",
                        "END:VEVENT"
                    ])

        ics_lines.append("END:VCALENDAR")
        return "\n".join(ics_lines)

    def _format_date_for_ics(self, date_str: str) -> str:
        """Format date string for ICS format"""
        if not date_str:
            return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        try:
            # Parse ISO format and convert to ICS format
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%Y%m%dT%H%M%SZ")
        except:
            return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _update_deletion_status(
        self,
        request_id: str,
        status: str,
        error_message: Optional[str] = None
    ):
        """Update deletion request status"""
        try:
            if self.firebase_service.db:
                update_data = {
                    'status': status,
                    'updated_at': datetime.utcnow().isoformat()
                }

                if status == 'completed':
                    update_data['completed_at'] = datetime.utcnow().isoformat()
                elif status == 'failed' and error_message:
                    update_data['error_message'] = error_message

                self.firebase_service.db.collection('deletion_requests')\
                    .document(request_id)\
                    .update(update_data)

        except Exception as e:
            self.logger.error(f"Error updating deletion status: {e}")


# Factory function to create deletion service
def create_deletion_service(firebase_service: FirebaseService) -> AccountDeletionService:
    return AccountDeletionService(firebase_service)