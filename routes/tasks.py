from flask import Blueprint, request, jsonify, current_app, Response, stream_template
from services.firebase_service import FirebaseService
from models.task import Task, TaskStatus, TaskPriority, Reminder
from datetime import datetime, timedelta
import logging
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import new validation and authentication utilities
from utils.auth import require_auth, require_user_access, check_user_access
from utils.validation import (
    TaskValidator, RequestValidator, ValidationError, 
    create_validation_error_response, create_authorization_error_response
)

tasks_bp = Blueprint('tasks', __name__)

def get_logger():
    return logging.getLogger('braindumpster.routes.tasks')

@tasks_bp.route('/create/batch', methods=['POST'])
@require_auth 
def create_tasks_batch():
    """Optimized batch task creation endpoint with better connection handling"""
    logger = get_logger()
    logger.info("📝 Creating tasks in batch mode...")
    
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate request data
        try:
            RequestValidator.validate_required_fields(data, ['tasks'])
            tasks_data = RequestValidator.validate_list_field(data, 'tasks', required=True, min_items=1, max_items=50)
        except ValidationError as e:
            return create_validation_error_response(e)
        
        user_id = request.user_id
        conversation_id = data.get('conversation_id')
        auto_approve = data.get('auto_approve', False)
        
        logger.info(f"👤 Batch creating {len(tasks_data)} tasks for user: {user_id}")
        
        firebase_service = current_app.firebase_service
        created_tasks = []
        errors = []
        
        # Process tasks in parallel using ThreadPoolExecutor
        def process_single_task(task_index, task_data):
            try:
                # Validate task data
                validated_task_data = TaskValidator.validate_task_data(task_data, task_index)
                
                # Create task object
                task = Task(
                    title=validated_task_data['title'],
                    description=validated_task_data['description'],
                    user_id=user_id,
                    due_date=validated_task_data.get('due_date'),
                    priority=validated_task_data['priority']
                )
                task.conversation_id = conversation_id
                task.status = TaskStatus.APPROVED if auto_approve else TaskStatus.PENDING
                
                # Process reminders
                if 'reminders' in task_data and task_data['reminders']:
                    for j, reminder_data in enumerate(task_data['reminders']):
                        reminder_time_str = reminder_data['reminder_time']
                        if isinstance(reminder_time_str, str):
                            if reminder_time_str.endswith('Z'):
                                reminder_time_str = reminder_time_str[:-1] + '+00:00'
                            reminder_time = datetime.fromisoformat(reminder_time_str)
                        else:
                            reminder_time = reminder_time_str
                        
                        reminder = Reminder(
                            task_id=None,
                            reminder_time=reminder_time,
                            message=reminder_data['message']
                        )
                        task.reminders.append(reminder)
                
                # Process subtasks
                if 'subtasks' in task_data and task_data['subtasks']:
                    task.subtasks = task_data['subtasks']
                
                # Save to Firebase
                task_dict = task.to_dict()
                task_id = firebase_service.save_task(task_dict)
                task_dict['id'] = task_id
                
                # Update reminder task_ids
                for reminder in task.reminders:
                    reminder.task_id = task_id
                task_dict['reminders'] = [r.to_dict() for r in task.reminders]
                
                return (task_index, task_dict, None)
                
            except Exception as e:
                logger.error(f"❌ Error processing task {task_index}: {str(e)}")
                return (task_index, None, str(e))
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, task_data in enumerate(tasks_data):
                future = executor.submit(process_single_task, i, task_data)
                futures.append(future)
            
            # Collect results as they complete
            for future in as_completed(futures):
                task_index, task_dict, error = future.result()
                if error:
                    errors.append({"task_index": task_index, "error": error})
                else:
                    created_tasks.append(task_dict)
        
        # Handle notifications and scheduling after all tasks are created
        if auto_approve and created_tasks:
            notification_service = getattr(current_app, 'notification_service', None)
            scheduler_service = getattr(current_app, 'scheduler_service', None)
            
            # Process notifications in background (non-blocking)
            if notification_service:
                for task_dict in created_tasks[:5]:  # Limit initial notifications
                    try:
                        task_obj = Task.from_dict(task_dict)
                        notification_service.send_task_approval_notification(task_obj)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send notification: {e}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"🎉 Batch created {len(created_tasks)} tasks in {elapsed_time:.2f}s")
        
        response_data = {
            "created_tasks": created_tasks,
            "count": len(created_tasks),
            "errors": errors,
            "processing_time": elapsed_time
        }
        
        # Force immediate response
        response = Response(
            json.dumps(response_data),
            status=201,
            mimetype='application/json'
        )
        response.headers['X-Processing-Time'] = str(elapsed_time)
        return response
        
    except Exception as e:
        logger.error(f"❌ Error in batch task creation: {str(e)}")
        return jsonify({"error": str(e)}), 500


@tasks_bp.route('/create', methods=['POST'])
@require_auth
def create_tasks():
    logger = get_logger()
    logger.info("📝 Creating new tasks...")
    
    # Add request start time for monitoring
    import time
    start_time = time.time()
    
    try:
        data = request.get_json()
        
        # Validate request data using new validation utilities
        try:
            RequestValidator.validate_required_fields(data, ['tasks'])
            tasks_data = RequestValidator.validate_list_field(data, 'tasks', required=True, min_items=1, max_items=50)
        except ValidationError as e:
            return create_validation_error_response(e)
        
        # Get user_id from authenticated token (set by require_auth decorator)
        user_id = request.user_id
        
        # Get optional fields
        conversation_id = data.get('conversation_id')
        auto_approve = data.get('auto_approve', False)
        
        logger.info(f"👤 User ID from token: {user_id}")
        logger.info(f"💬 Conversation ID: {conversation_id}")
        logger.info(f"📋 Number of tasks to create: {len(tasks_data)}")
        logger.info(f"✅ Auto-approve enabled: {auto_approve}")
        logger.debug(f"📦 Request data: {json.dumps(data, indent=2, default=str)}")
        
        if not user_id:
            logger.error("❌ Authentication failed: user_id not found in token")
            return jsonify({"error": "Authentication failed: user_id not found"}), 401
        
        firebase_service = current_app.firebase_service
        created_tasks = []
        
        for i, task_data in enumerate(tasks_data):
            task_start_time = time.time()
            logger.info(f"📝 Processing task {i+1}/{len(tasks_data)}: {task_data.get('title', 'Unknown')}")
            logger.debug(f"📦 Task data structure: {json.dumps(task_data, indent=2, default=str)}")
            
            # Validate task data using new validation utilities
            try:
                validated_task_data = TaskValidator.validate_task_data(task_data, i)
            except ValidationError as e:
                return create_validation_error_response(e)
            
            # Create task object
            try:
                task = Task(
                    title=validated_task_data['title'],
                    description=validated_task_data['description'],
                    user_id=user_id,
                    due_date=validated_task_data.get('due_date'),
                    priority=validated_task_data['priority'],
                    is_recurring=validated_task_data.get('is_recurring', False),
                    recurring_pattern=validated_task_data.get('recurring_pattern', {})
                )
                task.conversation_id = conversation_id
                logger.debug(f"✅ Task object created successfully: {task.title}")
                if task.is_recurring:
                    logger.info(f"🔄 Created recurring task with pattern: {task.recurring_pattern}")
            except Exception as e:
                logger.error(f"❌ Failed to create task object for task {i+1}: {e}")
                return jsonify({"error": f"Failed to create task {i+1}: {str(e)}"}), 400
            
            # Set status based on auto_approve flag
            if auto_approve:
                task.status = TaskStatus.APPROVED
                logger.info(f"✅ Task will be created as APPROVED: {task.title}")
            else:
                task.status = TaskStatus.PENDING
                logger.info(f"⏳ Task will be created as PENDING: {task.title}")
            
            # Process reminders if present
            if 'reminders' in task_data and task_data['reminders']:
                logger.info(f"⏰ Processing {len(task_data['reminders'])} reminders for task")
                for j, reminder_data in enumerate(task_data['reminders']):
                    try:
                        # Validate reminder structure
                        if not reminder_data.get('reminder_time'):
                            logger.error(f"❌ Reminder {j+1} for task {i+1} missing reminder_time")
                            return jsonify({"error": f"Reminder {j+1} for task {i+1} missing reminder_time"}), 400
                        
                        if not reminder_data.get('message'):
                            logger.error(f"❌ Reminder {j+1} for task {i+1} missing message")
                            return jsonify({"error": f"Reminder {j+1} for task {i+1} missing message"}), 400
                        
                        # Parse reminder time
                        reminder_time_str = reminder_data['reminder_time']
                        if isinstance(reminder_time_str, str):
                            # Handle various date formats
                            if reminder_time_str.endswith('Z'):
                                reminder_time_str = reminder_time_str[:-1] + '+00:00'
                            reminder_time = datetime.fromisoformat(reminder_time_str)
                        else:
                            reminder_time = reminder_time_str
                        
                        reminder = Reminder(
                            task_id=None,  # Will be set after task is saved
                            reminder_time=reminder_time,
                            message=reminder_data['message']
                        )
                        task.reminders.append(reminder)
                        logger.debug(f"⏰ Added reminder {j+1}: {reminder_data['reminder_time']} - {reminder_data['message']}")
                        
                    except (ValueError, TypeError, KeyError) as e:
                        logger.error(f"❌ Invalid reminder {j+1} for task {i+1}: {e}")
                        logger.error(f"❌ Reminder data: {json.dumps(reminder_data, default=str)}")
                        return jsonify({"error": f"Invalid reminder {j+1} for task {i+1}: {str(e)}"}), 400
            
            # Process subtasks if present
            if 'subtasks' in task_data and task_data['subtasks']:
                logger.info(f"📝 Processing {len(task_data['subtasks'])} subtasks")
                task.subtasks = task_data['subtasks']
            
            # Save to Firebase
            logger.info(f"💾 Saving task to Firebase: {task.title}")
            task_dict = task.to_dict()
            task_id = firebase_service.save_task(task_dict)
            task_dict['id'] = task_id
            logger.info(f"✅ Task saved with ID: {task_id}")
            
            # Update reminder task_ids
            for reminder in task.reminders:
                reminder.task_id = task_id
            
            # Update task dict with correct task_id in reminders
            task_dict['reminders'] = [r.to_dict() for r in task.reminders]
            logger.debug(f"💾 Task saved with {len(task.reminders)} reminders: {[r.to_dict() for r in task.reminders]}")
            
            created_tasks.append(task_dict)
            task_elapsed = time.time() - task_start_time
            logger.info(f"✅ Task {i+1} completed: {task.title} (took {task_elapsed:.2f}s)")
            
            # If auto-approved and has reminders, schedule them immediately
            if auto_approve and task.reminders:
                scheduler_service = getattr(current_app, 'scheduler_service', None)
                if scheduler_service:
                    scheduler_service.schedule_reminder_for_task(task)
                    logger.info(f"⏰ Scheduled {len(task.reminders)} reminders for auto-approved task: {task.title}")
                else:
                    logger.warning("⚠️ Scheduler service not available for reminder scheduling")
        
        total_elapsed = time.time() - start_time
        logger.info(f"🎉 Successfully created {len(created_tasks)} tasks for user {user_id} (total time: {total_elapsed:.2f}s)")
        
        # Send notifications for auto-approved tasks
        if auto_approve and created_tasks:
            notification_service = getattr(current_app, 'notification_service', None)
            if notification_service:
                for task_dict in created_tasks:
                    # Convert back to Task object for notification
                    task_obj = Task.from_dict(task_dict)
                    try:
                        notification_service.send_task_approval_notification(task_obj)
                        logger.info(f"📱 Sent approval notification for: {task_obj.title}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send approval notification for {task_obj.title}: {e}")
        
        response = jsonify({
            "created_tasks": created_tasks,
            "count": len(created_tasks),
            "processing_time": time.time() - start_time
        })
        response.status_code = 201
        
        # Ensure response is sent immediately
        response.direct_passthrough = False
        return response
        
    except Exception as e:
        logger.error(f"❌ Error creating tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/user/<user_id>', methods=['GET'])
@require_auth
def get_user_tasks(user_id):
    logger = get_logger()
    logger.info(f"📋 Getting tasks for user: {user_id}")
    
    # Debug: Log the user ID comparison
    authenticated_user_id = request.user_id
    logger.info(f"🔍 Authentication check: Token user_id='{authenticated_user_id}', URL user_id='{user_id}'")
    
    # Security check: Ensure users can only access their own tasks
    if authenticated_user_id != user_id:
        logger.warning(f"❌ Authorization failed: User '{authenticated_user_id}' tried to access tasks for user '{user_id}'")
        return jsonify({"error": "Unauthorized: Cannot access another user's tasks"}), 403
    
    try:
            
        status = request.args.get('status')
        # Handle comma-separated status values from Flutter
        if status and ',' in status:
            status = [s.strip() for s in status.split(',')]
            logger.debug(f"🔍 Converted comma-separated status to list: {status}")
        
        # Get language parameter for localization
        language = request.args.get('language', 'en')
        logger.debug(f"🌍 Language requested: {language}")
        
        limit = min(int(request.args.get('limit', 50)), 100)  # Cap at 100 to prevent timeouts
        
        # ⏰ New time filtering parameters for dashboard
        include_past_due = request.args.get('include_past_due', 'true').lower() == 'true'
        include_past_reminders = request.args.get('include_past_reminders', 'true').lower() == 'true'
        filter_by_date = request.args.get('filter_by_date')  # 'today' for dashboard
        
        logger.info(f"🔍 Filters - Status: {status}, Limit: {limit}")
        logger.info(f"🕐 Time Filters - Past Due: {include_past_due}, Past Reminders: {include_past_reminders}, Date Filter: {filter_by_date}")
        
        firebase_service = current_app.firebase_service
        
        # Track query performance without signal-based timeout
        import time
        start_time = time.time()
        
        tasks = firebase_service.get_user_tasks(
            user_id, 
            status,
            include_past_due=include_past_due,
            include_past_reminders=include_past_reminders,
            filter_by_date=filter_by_date
        )
        
        query_time = time.time() - start_time
        logger.info(f"⚡ Firebase query completed in {query_time:.2f}s")
        
        logger.info(f"📊 Found {len(tasks)} tasks from Firebase")
        
        # Limit results
        tasks = tasks[:limit]
        
        logger.info(f"🎯 Returning {len(tasks)} tasks (after limit)")
        logger.debug(f"📋 Task summaries: {[{'id': t.get('id'), 'title': t.get('title'), 'status': t.get('status')} for t in tasks[:5]]}")
        
        # Apply localization to tasks
        localization_service = getattr(current_app, 'localization_service', None)
        if localization_service and language != 'en':
            try:
                tasks = localization_service.localize_task_list(tasks, language)
                logger.info(f"🌍 Applied {language} localization to {len(tasks)} tasks")
            except Exception as e:
                logger.warning(f"⚠️ Failed to localize tasks: {e}")
        
        # Use streaming response for large datasets
        if len(tasks) > 50:
            logger.info(f"📊 Large dataset detected ({len(tasks)} tasks), using chunked response")
            
            def generate_chunked_response():
                yield '{"tasks": ['
                for i, task in enumerate(tasks):
                    if i > 0:
                        yield ','
                    yield json.dumps(task, default=str)
                yield f'], "count": {len(tasks)}}}'
            
            from flask import Response
            return Response(
                generate_chunked_response(),
                mimetype='application/json',
                headers={
                    'X-Task-Count': str(len(tasks)),
                    'X-Processing-Time': f"{time.time() - start_time:.2f}s"
                }
            )
        else:
            return jsonify({
                "tasks": tasks,
                "count": len(tasks)
            })
        
    except Exception as e:
        logger.error(f"❌ Error getting user tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>', methods=['PUT'])
@require_auth
def update_task(task_id):
    try:
        data = request.get_json()
        
        # Prepare updates
        updates = {}
        if 'status' in data:
            updates['status'] = data['status']
        if 'title' in data:
            updates['title'] = data['title']
        if 'description' in data:
            updates['description'] = data['description']
        if 'due_date' in data:
            updates['due_date'] = data['due_date']
        if 'priority' in data:
            updates['priority'] = data['priority']
        
        updates['updated_at'] = datetime.utcnow().isoformat()
        
        firebase_service = current_app.firebase_service
        firebase_service.update_task(task_id, updates)
        
        return jsonify({"message": "Task updated successfully"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>', methods=['DELETE'])
@require_auth
def delete_task(task_id):
    logger = get_logger()
    logger.info(f"🗑️ Soft deleting task: {task_id}")
    
    try:
        firebase_service = current_app.firebase_service
        
        # Soft delete by updating status to DELETED
        updates = {
            'status': TaskStatus.DELETED.value,
            'updated_at': datetime.utcnow().isoformat(),
            'deleted_at': datetime.utcnow().isoformat()
        }
        
        firebase_service.update_task(task_id, updates)
        logger.info(f"✅ Task {task_id} soft deleted successfully")
        
        return jsonify({"message": "Task deleted successfully"})
        
    except Exception as e:
        logger.error(f"❌ Error soft deleting task {task_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/approve', methods=['POST'])
@require_auth
def approve_tasks():
    logger = get_logger()
    logger.info("✅ Approving tasks...")
    
    try:
        data = request.get_json()
        
        if not data:
            logger.error("❌ Request body is missing or invalid JSON")
            return jsonify({"error": "Request body must be valid JSON"}), 400
        
        task_ids = data.get('task_ids', [])
        
        # Get user_id from authenticated token (set by require_auth decorator)
        user_id = request.user_id
        
        logger.info(f"👤 User ID from token: {user_id}")
        logger.info(f"📝 Task IDs to approve: {task_ids}")
        
        if not user_id:
            logger.error("❌ Authentication failed: user_id not found in token")
            return jsonify({"error": "Authentication failed: user_id not found"}), 401
            
        if not task_ids:
            logger.error("❌ Missing required field: task_ids")
            return jsonify({"error": "task_ids field is required"}), 400
        
        firebase_service = current_app.firebase_service
        notification_service = getattr(current_app, 'notification_service', None)
        scheduler_service = getattr(current_app, 'scheduler_service', None)
        
        approved_tasks = []
        
        for i, task_id in enumerate(task_ids):
            logger.info(f"✅ Approving task {i+1}/{len(task_ids)}: {task_id}")
            
            # Update task status
            firebase_service.update_task(task_id, {
                'status': TaskStatus.APPROVED.value,
                'updated_at': datetime.utcnow().isoformat()
            })
            
            # Get the updated task for notifications
            task_data = firebase_service.get_task(task_id)
            if task_data and notification_service:
                try:
                    # Convert to Task object
                    task = Task.from_dict(task_data)
                    
                    # Send approval notification
                    notification_sent = notification_service.send_task_approval_notification(task)
                    if notification_sent:
                        logger.info(f"📱 Approval notification sent for task: {task.title}")
                    else:
                        logger.warning(f"⚠️ Failed to send approval notification for task: {task.title}")
                    
                    # Schedule reminders if scheduler is available
                    if scheduler_service:
                        scheduler_service.schedule_reminder_for_task(task)
                        logger.info(f"⏰ Reminders scheduled for task: {task.title}")
                    
                    approved_tasks.append({
                        'id': task.id,
                        'title': task.title,
                        'notification_sent': notification_sent,
                        'reminders_scheduled': scheduler_service is not None
                    })
                    
                except Exception as e:
                    logger.error(f"❌ Error processing notifications for task {task_id}: {str(e)}")
                    approved_tasks.append({
                        'id': task_id,
                        'notification_sent': False,
                        'reminders_scheduled': False,
                        'error': str(e)
                    })
            else:
                approved_tasks.append({
                    'id': task_id,
                    'notification_sent': False,
                    'reminders_scheduled': False
                })
        
        logger.info(f"🎉 Successfully approved {len(task_ids)} tasks for user {user_id}")
        return jsonify({
            "message": f"Approved {len(task_ids)} tasks",
            "approved_tasks": approved_tasks,
            "notification_service_available": notification_service is not None,
            "scheduler_service_available": scheduler_service is not None
        })
        
    except Exception as e:
        logger.error(f"❌ Error approving tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>', methods=['GET'])
@require_auth
def get_task_stats(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting task statistics for user: {user_id}")
    
    try:
        # Security: Ensure user can only access their own statistics
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s stats")
            return jsonify({"error": "Unauthorized: Cannot access another user's statistics"}), 403
            
        if not user_id:
            logger.error("❌ Missing user_id parameter")
            return jsonify({"error": "user_id is required"}), 400
            
        firebase_service = current_app.firebase_service
        logger.info(f"🔥 Firebase service available: {firebase_service is not None}")
        
        all_tasks = firebase_service.get_user_tasks(user_id)
        logger.info(f"📋 Retrieved {len(all_tasks)} tasks for user {user_id}")
        
        # Calculate today's stats
        from datetime import date
        today = date.today().isoformat()
        today_tasks = [t for t in all_tasks if (t.get('due_date') or '').startswith(today)]
        
        stats = {
            "total": len(all_tasks),
            "todayCount": len(today_tasks),
            "completedToday": len([t for t in today_tasks if t.get('status') == 'completed']),
            "pending": len([t for t in all_tasks if t.get('status') == 'pending']),
            "approved": len([t for t in all_tasks if t.get('status') == 'approved']),
            "completed": len([t for t in all_tasks if t.get('status') == 'completed']),
            "cancelled": len([t for t in all_tasks if t.get('status') == 'cancelled']),
            "by_priority": {
                "urgent": len([t for t in all_tasks if t.get('priority') == 'urgent']),
                "high": len([t for t in all_tasks if t.get('priority') == 'high']),
                "medium": len([t for t in all_tasks if t.get('priority') == 'medium']),
                "low": len([t for t in all_tasks if t.get('priority') == 'low'])
            }
        }
        
        logger.info(f"📊 Stats calculated: {stats}")
        return jsonify(stats), 200
        
    except Exception as e:
        logger.error(f"❌ Error getting task stats: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/analytics/<user_id>', methods=['GET'])
@require_auth
def get_task_analytics(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting comprehensive task analytics for user: {user_id}")
    
    try:
        # Security: Ensure user can only access their own analytics
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s analytics")
            return jsonify({"error": "Unauthorized: Cannot access another user's analytics"}), 403
            
        # Get query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        days = int(request.args.get('days', 30))
        
        from datetime import datetime, timedelta, timedelta, date
        import json
        
        # Set default date range
        end_date = datetime.fromisoformat(end_date_str) if end_date_str else datetime.now()
        start_date = datetime.fromisoformat(start_date_str) if start_date_str else end_date - timedelta(days=days)
        
        logger.info(f"📅 Analytics period: {start_date} to {end_date}")
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        logger.info(f"📋 Retrieved {len(all_tasks)} tasks for analytics")
        
        # Convert string dates to datetime objects for calculations
        for task in all_tasks:
            if task.get('created_at'):
                try:
                    task['created_at_dt'] = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
                except:
                    task['created_at_dt'] = datetime.now()
            if task.get('due_date'):
                try:
                    task['due_date_dt'] = datetime.fromisoformat(task['due_date'])
                except:
                    task['due_date_dt'] = None
            if task.get('updated_at'):
                try:
                    task['updated_at_dt'] = datetime.fromisoformat(task['updated_at'].replace('Z', '+00:00'))
                except:
                    task['updated_at_dt'] = datetime.now()
        
        # Calculate status distribution
        status_distribution = {}
        for status in ['pending', 'approved', 'completed', 'cancelled']:
            status_distribution[status] = len([t for t in all_tasks if t.get('status') == status])
        
        # Calculate priority distribution
        priority_distribution = {}
        for priority in ['urgent', 'high', 'medium', 'low']:
            priority_distribution[priority] = len([t for t in all_tasks if t.get('priority') == priority])
        
        # Calculate category distribution (if categories exist)
        category_distribution = {}
        categories = set(t.get('category', 'uncategorized') for t in all_tasks if t.get('category'))
        for category in categories:
            category_distribution[category] = len([t for t in all_tasks if t.get('category') == category])
        
        # Calculate tasks in period
        period_tasks = [t for t in all_tasks if 
                       t.get('created_at_dt') and 
                       start_date <= t['created_at_dt'] <= end_date]
        
        completed_in_period = len([t for t in period_tasks if t.get('status') == 'completed'])
        
        # Calculate overdue tasks
        now = datetime.now()
        overdue_tasks = [t for t in all_tasks if 
                        t.get('due_date_dt') and 
                        t['due_date_dt'] < now and 
                        t.get('status') not in ['completed', 'cancelled']]
        
        # Calculate completion rate
        total_tasks = len(all_tasks)
        completed_tasks = status_distribution.get('completed', 0)
        completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
        
        # Calculate productivity score
        overdue_count = len(overdue_tasks)
        productivity_score = _calculate_productivity_score(completion_rate, overdue_count, total_tasks)
        
        # Calculate completion streak
        completion_streak = _calculate_completion_streak(all_tasks)
        
        # Calculate active tasks
        active_tasks = status_distribution.get('pending', 0) + status_distribution.get('approved', 0)
        
        analytics = {
            "total_tasks": total_tasks,
            "active_tasks": active_tasks,
            "completed_tasks": completed_tasks,
            "overdue_tasks_count": overdue_count,
            "status_distribution": status_distribution,
            "category_distribution": category_distribution,
            "priority_distribution": priority_distribution,
            "completion_rate": completion_rate,
            "completed_in_period": completed_in_period,
            "productivity_score": productivity_score,
            "completion_streak": completion_streak,
            "analyzed_period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days
            },
            "overdue_percentage": overdue_count / total_tasks if total_tasks > 0 else 0.0,
            "active_percentage": active_tasks / total_tasks if total_tasks > 0 else 0.0,
            "productivity_grade": _get_productivity_grade(productivity_score)
        }
        
        logger.info(f"📊 Comprehensive analytics calculated for {total_tasks} tasks")
        return jsonify(analytics), 200
        
    except Exception as e:
        logger.error(f"❌ Error calculating analytics: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/trends/<user_id>', methods=['GET'])
@require_auth
def get_task_trends(user_id):
    logger = get_logger()
    logger.info(f"📈 Getting task trends for user: {user_id}")
    
    try:
        # Security: Ensure user can only access their own trends
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s trends")
            return jsonify({"error": "Unauthorized: Cannot access another user's trends"}), 403
        
        days = int(request.args.get('days', 30))
        
        from datetime import datetime, timedelta, timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        logger.info(f"📅 Trends period: {days} days ({start_date} to {end_date})")
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        # Convert string dates to datetime objects
        for task in all_tasks:
            if task.get('created_at'):
                try:
                    task['created_at_dt'] = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
                except:
                    task['created_at_dt'] = datetime.now()
            if task.get('due_date'):
                try:
                    task['due_date_dt'] = datetime.fromisoformat(task['due_date'])
                except:
                    task['due_date_dt'] = None
            if task.get('updated_at'):
                try:
                    task['updated_at_dt'] = datetime.fromisoformat(task['updated_at'].replace('Z', '+00:00'))
                except:
                    task['updated_at_dt'] = datetime.now()
        
        # Calculate daily data
        daily_data = {}
        total_created = 0
        total_completed = 0
        total_overdue = 0
        
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            # Tasks created on this day
            created_count = len([t for t in all_tasks if 
                               t.get('created_at_dt') and 
                               day_start <= t['created_at_dt'] < day_end])
            
            # Tasks completed on this day (check updated_at for completion)
            completed_count = len([t for t in all_tasks if 
                                 t.get('status') == 'completed' and
                                 t.get('updated_at_dt') and
                                 day_start <= t['updated_at_dt'] < day_end])
            
            # Tasks that became overdue on this day
            overdue_count = len([t for t in all_tasks if 
                               t.get('due_date_dt') and
                               day_start <= t['due_date_dt'] < day_end and
                               t.get('status') not in ['completed', 'cancelled']])
            
            daily_data[current_date.isoformat()] = {
                "date": current_date.isoformat(),
                "tasks_created": created_count,
                "tasks_completed": completed_count,
                "tasks_overdue": overdue_count
            }
            
            total_created += created_count
            total_completed += completed_count
            total_overdue += overdue_count
        
        # Calculate averages
        average_daily = {
            "created": total_created / days if days > 0 else 0.0,
            "completed": total_completed / days if days > 0 else 0.0,
            "overdue": total_overdue / days if days > 0 else 0.0
        }
        
        trends = {
            "daily_data": daily_data,
            "period_days": days,
            "average_daily": average_daily,
            "total_created": total_created,
            "total_completed": total_completed,
            "total_overdue": total_overdue
        }
        
        logger.info(f"📈 Trends calculated for {days} days")
        return jsonify(trends), 200
        
    except Exception as e:
        logger.error(f"❌ Error calculating trends: {str(e)}")
        return jsonify({"error": str(e)}), 500

def _calculate_productivity_score(completion_rate, overdue_count, total_tasks):
    """Calculate productivity score based on completion rate and overdue tasks"""
    if total_tasks == 0:
        return 0.0
    
    # Base score from completion rate (0-70 points)
    score = completion_rate * 70
    
    # Penalty for overdue tasks (up to -30 points)
    overdue_ratio = overdue_count / total_tasks
    score -= overdue_ratio * 30
    
    # Bonus for high completion rate (up to +30 points)
    if completion_rate > 0.8:
        score += (completion_rate - 0.8) * 150  # 30 points for perfect completion
    
    return max(0.0, min(100.0, score)) / 100.0  # Normalize to 0-1

def _calculate_completion_streak(all_tasks):
    """Calculate current completion streak in days"""
    from datetime import datetime, timedelta, timedelta
    
    try:
        today = datetime.now()
        streak = 0
        
        for i in range(365):  # Max 1 year streak
            check_date = today - timedelta(days=i)
            day_start = check_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            
            # Check if any tasks were completed on this day
            completed_on_day = any(
                t.get('status') == 'completed' and
                t.get('updated_at') and
                day_start <= datetime.fromisoformat(t['updated_at'].replace('Z', '+00:00')) < day_end
                for t in all_tasks
            )
            
            if completed_on_day:
                streak += 1
            else:
                break
        
        return streak
    except Exception:
        return 0

def _get_productivity_grade(score):
    """Convert productivity score to letter grade"""
    if score >= 0.9:
        return 'A+'
    elif score >= 0.8:
        return 'A'
    elif score >= 0.7:
        return 'B+'
    elif score >= 0.6:
        return 'B'
    elif score >= 0.5:
        return 'C+'
    elif score >= 0.4:
        return 'C'
    else:
        return 'D'

# New enhanced endpoints for Flutter client

@tasks_bp.route('/user/<user_id>/filtered', methods=['GET'])
@require_auth
def get_user_tasks_filtered(user_id):
    logger = get_logger()
    logger.info(f"📋 Getting filtered tasks for user: {user_id}")
    
    try:
        # Security: Ensure user can only access their own tasks
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s tasks")
            return jsonify({"error": "Unauthorized: Cannot access another user's tasks"}), 403
            
        # Get filter parameters
        status = request.args.get('status')
        category = request.args.get('category')
        priority = request.args.get('priority')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        include_completed = request.args.get('include_completed', 'true').lower() == 'true'
        sort_order = request.args.get('sort_order', 'due_date')
        limit = int(request.args.get('limit', 50))
        
        logger.info(f"🔍 Filters - Status: {status}, Category: {category}, Priority: {priority}")
        
        firebase_service = current_app.firebase_service
        
        # Start with all user tasks
        all_tasks = firebase_service.get_user_tasks(user_id)
        filtered_tasks = []
        
        for task in all_tasks:
            # Apply filters
            if status and task.get('status') != status:
                continue
                
            if category and task.get('category') != category:
                continue
                
            if priority and task.get('priority') != priority:
                continue
                
            if not include_completed and task.get('status') == 'completed':
                continue
                
            # Date range filtering
            if start_date or end_date:
                task_date = task.get('due_date')
                if task_date:
                    try:
                        from datetime import datetime, timedelta
                        if isinstance(task_date, str):
                            task_dt = datetime.fromisoformat(task_date.replace('Z', '+00:00'))
                        else:
                            task_dt = task_date
                        
                        if start_date:
                            start_dt = datetime.fromisoformat(start_date)
                            if task_dt < start_dt:
                                continue
                                
                        if end_date:
                            end_dt = datetime.fromisoformat(end_date)
                            if task_dt > end_dt:
                                continue
                    except Exception as e:
                        logger.warning(f"⚠️ Date parsing error: {e}")
                        continue
            
            filtered_tasks.append(task)
        
        # Sort tasks
        if sort_order == 'due_date':
            filtered_tasks.sort(key=lambda t: t.get('due_date') or '9999-12-31')
        elif sort_order == 'priority':
            priority_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
            filtered_tasks.sort(key=lambda t: priority_order.get(t.get('priority', 'medium'), 2))
        elif sort_order == 'created_at':
            filtered_tasks.sort(key=lambda t: t.get('created_at', ''), reverse=True)
        
        # Apply limit
        filtered_tasks = filtered_tasks[:limit]
        
        logger.info(f"🎯 Returning {len(filtered_tasks)} filtered tasks")
        
        return jsonify({
            "tasks": filtered_tasks,
            "count": len(filtered_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting filtered tasks: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/batch', methods=['PUT'])
@require_auth
def batch_update_tasks():
    logger = get_logger()
    logger.info("📝 Batch updating tasks...")
    
    try:
        data = request.get_json()
        tasks_data = data.get('tasks', [])
        
        if not tasks_data:
            return jsonify({"error": "No tasks provided"}), 400
        
        logger.info(f"📝 Updating {len(tasks_data)} tasks")
        
        firebase_service = current_app.firebase_service
        updated_tasks = []
        failed_tasks = []
        
        for task_data in tasks_data:
            task_id = task_data.get('id')
            if not task_id:
                failed_tasks.append({"error": "Missing task ID", "data": task_data})
                continue
            
            try:
                # Remove id from updates
                updates = {k: v for k, v in task_data.items() if k != 'id'}
                updates['updated_at'] = datetime.utcnow().isoformat()
                
                firebase_service.update_task(task_id, updates)
                updated_tasks.append(task_id)
                logger.info(f"✅ Updated task: {task_id}")
                
            except Exception as e:
                logger.error(f"❌ Failed to update task {task_id}: {e}")
                failed_tasks.append({"task_id": task_id, "error": str(e)})
        
        return jsonify({
            "updated_tasks": updated_tasks,
            "failed_tasks": failed_tasks,
            "success_count": len(updated_tasks),
            "failure_count": len(failed_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ Error in batch update: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/batch', methods=['DELETE'])
@require_auth
def batch_delete_tasks():
    logger = get_logger()
    logger.info("🗑️ Batch soft deleting tasks...")
    
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        
        if not task_ids:
            return jsonify({"error": "No task IDs provided"}), 400
        
        logger.info(f"🗑️ Soft deleting {len(task_ids)} tasks")
        
        firebase_service = current_app.firebase_service
        deleted_tasks = []
        failed_tasks = []
        
        for task_id in task_ids:
            try:
                # Soft delete by updating status to DELETED
                updates = {
                    'status': TaskStatus.DELETED.value,
                    'updated_at': datetime.utcnow().isoformat(),
                    'deleted_at': datetime.utcnow().isoformat()
                }
                
                firebase_service.update_task(task_id, updates)
                deleted_tasks.append(task_id)
                logger.info(f"✅ Soft deleted task: {task_id}")
                
            except Exception as e:
                logger.error(f"❌ Failed to soft delete task {task_id}: {e}")
                failed_tasks.append({"task_id": task_id, "error": str(e)})
        
        return jsonify({
            "deleted_tasks": deleted_tasks,
            "failed_tasks": failed_tasks,
            "success_count": len(deleted_tasks),
            "failure_count": len(failed_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ Error in batch soft delete: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/complete', methods=['POST'])
@require_auth
def mark_tasks_completed():
    logger = get_logger()
    logger.info("✅ Marking tasks as completed...")
    
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        
        if not task_ids:
            return jsonify({"error": "No task IDs provided"}), 400
        
        logger.info(f"✅ Marking {len(task_ids)} tasks as completed")
        
        firebase_service = current_app.firebase_service
        notification_service = getattr(current_app, 'notification_service', None)
        completed_tasks = []
        failed_tasks = []
        
        for task_id in task_ids:
            try:
                # Update task status
                updates = {
                    'status': TaskStatus.COMPLETED.value,
                    'updated_at': datetime.utcnow().isoformat(),
                    'completed_at': datetime.utcnow().isoformat()
                }
                
                firebase_service.update_task(task_id, updates)
                
                # Send completion notification if service available
                if notification_service:
                    try:
                        task_data = firebase_service.get_task(task_id)
                        if task_data:
                            task_obj = Task.from_dict(task_data)
                            notification_service.send_task_completion_notification(task_obj)
                            logger.info(f"📱 Completion notification sent for: {task_obj.title}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to send completion notification: {e}")
                
                completed_tasks.append(task_id)
                logger.info(f"✅ Completed task: {task_id}")
                
            except Exception as e:
                logger.error(f"❌ Failed to complete task {task_id}: {e}")
                failed_tasks.append({"task_id": task_id, "error": str(e)})
        
        return jsonify({
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks,
            "success_count": len(completed_tasks),
            "failure_count": len(failed_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ Error marking tasks as completed: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>/status', methods=['GET'])
@require_auth
def get_task_count_by_status(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting task count by status for user: {user_id}")
    
    try:
        # Security check
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        status_counts = {}
        for task in all_tasks:
            status = task.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return jsonify(status_counts)
        
    except Exception as e:
        logger.error(f"❌ Error getting status counts: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>/category', methods=['GET'])
@require_auth
def get_task_count_by_category(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting task count by category for user: {user_id}")
    
    try:
        # Security check
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        category_counts = {}
        for task in all_tasks:
            category = task.get('category', 'uncategorized')
            category_counts[category] = category_counts.get(category, 0) + 1
        
        return jsonify(category_counts)
        
    except Exception as e:
        logger.error(f"❌ Error getting category counts: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>/priority', methods=['GET'])
@require_auth
def get_task_count_by_priority(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting task count by priority for user: {user_id}")
    
    try:
        # Security check
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        priority_counts = {}
        for task in all_tasks:
            priority = task.get('priority', 'medium')
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
        
        return jsonify(priority_counts)
        
    except Exception as e:
        logger.error(f"❌ Error getting priority counts: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>/completed', methods=['GET'])
@require_auth
def get_completed_tasks_count(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting completed tasks count for user: {user_id}")
    
    try:
        # Security check
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id, status='completed')
        
        from datetime import datetime, timedelta
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        count = 0
        for task in all_tasks:
            completed_at = task.get('completed_at') or task.get('updated_at')
            if completed_at:
                try:
                    if isinstance(completed_at, str):
                        task_dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                    else:
                        task_dt = completed_at
                    
                    if start_dt <= task_dt <= end_dt:
                        count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error: {e}")
                    continue
        
        return jsonify({
            "completed_count": count,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting completed tasks count: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/stats/<user_id>/completion-rate', methods=['GET'])
@require_auth
def get_completion_rate(user_id):
    logger = get_logger()
    logger.info(f"📊 Getting completion rate for user: {user_id}")
    
    try:
        # Security check
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized"}), 403
        
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date are required"}), 400
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        from datetime import datetime, timedelta
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
        
        total_tasks = 0
        completed_tasks = 0
        
        for task in all_tasks:
            created_at = task.get('created_at')
            if created_at:
                try:
                    if isinstance(created_at, str):
                        task_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    else:
                        task_dt = created_at
                    
                    if start_dt <= task_dt <= end_dt:
                        total_tasks += 1
                        if task.get('status') == 'completed':
                            completed_tasks += 1
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error: {e}")
                    continue
        
        completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
        
        return jsonify({
            "completion_rate": completion_rate,
            "completed_tasks": completed_tasks,
            "total_tasks": total_tasks,
            "period": {
                "start_date": start_date,
                "end_date": end_date
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting completion rate: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/reminders/<user_id>', methods=['GET'])
@require_auth
def get_user_reminders(user_id):
    try:
        # Security: Ensure user can only access their own reminders
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot access another user's reminders"}), 403
            
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        # Extract all reminders from tasks
        all_reminders = []
        for task in all_tasks:
            if task.get('status') in ['pending', 'approved']:  # Only active tasks
                reminders = task.get('reminders', [])
                for reminder in reminders:
                    if not reminder.get('sent', False):  # Only unsent reminders
                        reminder_with_task = reminder.copy()
                        reminder_with_task['task_title'] = task.get('title', '')
                        reminder_with_task['task_id'] = task.get('id', '')
                        all_reminders.append(reminder_with_task)
        
        # Sort reminders by time
        all_reminders.sort(key=lambda r: r.get('reminder_time', ''))
        
        return jsonify({
            "reminders": all_reminders,
            "count": len(all_reminders)
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>/stop-reminders', methods=['PUT'])
@require_auth
def stop_task_reminders(task_id):
    try:
        firebase_service = current_app.firebase_service

        # Get the task first
        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        task_doc = firebase_service.db.collection('tasks').document(task_id).get()
        if not task_doc.exists:
            return jsonify({"error": "Task not found"}), 404

        task_data = task_doc.to_dict()

        # Mark all reminders as sent (inactive)
        if 'reminders' in task_data and task_data['reminders']:
            for reminder in task_data['reminders']:
                reminder['sent'] = True

            # Update the task with modified reminders
            firebase_service.update_task(task_id, {
                'reminders': task_data['reminders'],
                'updated_at': datetime.utcnow().isoformat()
            })

        return jsonify({"message": "All reminders stopped for this task"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/<task_id>/reminders/<reminder_id>', methods=['DELETE'])
@require_auth
def delete_single_reminder(task_id, reminder_id):
    """Delete/deactivate a single reminder for a task"""
    logger = get_logger()
    logger.info(f"🗑️ Deleting single reminder: {reminder_id} for task: {task_id}")

    try:
        firebase_service = current_app.firebase_service

        # Get the task first
        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500

        task_doc = firebase_service.db.collection('tasks').document(task_id).get()
        if not task_doc.exists:
            return jsonify({"error": "Task not found"}), 404

        task_data = task_doc.to_dict()

        # Find and mark the specific reminder as sent (inactive)
        if 'reminders' in task_data and task_data['reminders']:
            reminder_found = False
            for reminder in task_data['reminders']:
                # Match by reminder ID or by reminder time as fallback
                if (reminder.get('id') == reminder_id or
                    reminder.get('reminder_time') == reminder_id or
                    str(reminder.get('reminder_time')) == reminder_id):
                    reminder['sent'] = True
                    reminder_found = True
                    logger.info(f"✅ Marked reminder as sent: {reminder.get('message', 'Unknown')}")
                    break

            if not reminder_found:
                logger.warning(f"❌ Reminder not found: {reminder_id}")
                return jsonify({"error": "Reminder not found"}), 404

            # Update the task with modified reminders
            firebase_service.update_task(task_id, {
                'reminders': task_data['reminders'],
                'updated_at': datetime.utcnow().isoformat()
            })

            logger.info(f"✅ Successfully deleted reminder {reminder_id} for task {task_id}")
            return jsonify({
                "message": "Reminder deleted successfully",
                "reminder_id": reminder_id,
                "task_id": task_id
            })
        else:
            logger.warning(f"❌ No reminders found for task: {task_id}")
            return jsonify({"error": "No reminders found for this task"}), 404

    except Exception as e:
        logger.error(f"❌ Error deleting single reminder: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/debug/<user_id>', methods=['GET'])
@require_auth
def debug_user_tasks(user_id):
    """Debug endpoint to inspect raw task data structure"""
    logger = get_logger()
    logger.info(f"🔍 DEBUG: Inspecting tasks for user: {user_id}")
    
    try:
        # Security: Ensure user can only debug their own tasks
        if user_id != request.user_id:
            return jsonify({"error": "Unauthorized: Cannot debug another user's tasks"}), 403
            
        firebase_service = current_app.firebase_service
        
        if not firebase_service.db:
            return jsonify({"error": "Firebase not configured"}), 500
        
        # Get raw tasks from Firebase
        query = firebase_service.db.collection('tasks').where('user_id', '==', user_id).limit(10)
        docs = query.stream()
        
        debug_data = {
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "tasks": []
        }
        
        for doc in docs:
            task_data = doc.to_dict()
            task_data['id'] = doc.id
            
            # Add debug info
            task_debug = {
                "id": doc.id,
                "title": task_data.get('title', 'N/A'),
                "status": task_data.get('status', 'N/A'),
                "created_at": task_data.get('created_at', 'N/A'),
                "updated_at": task_data.get('updated_at', 'N/A'),
                "reminders_raw": task_data.get('reminders', []),
                "reminders_count": len(task_data.get('reminders', [])),
                "reminders_type": str(type(task_data.get('reminders', []))),
                "all_keys": list(task_data.keys()),
                "raw_data": task_data
            }
            
            # Test Task.from_dict conversion
            try:
                task_obj = Task.from_dict(task_data)
                task_debug["from_dict_reminders_count"] = len(task_obj.reminders)
                task_debug["from_dict_reminders"] = [r.to_dict() for r in task_obj.reminders]
                task_debug["from_dict_success"] = True
            except Exception as e:
                task_debug["from_dict_error"] = str(e)
                task_debug["from_dict_success"] = False
            
            debug_data["tasks"].append(task_debug)
        
        logger.info(f"🔍 DEBUG: Found {len(debug_data['tasks'])} tasks for inspection")
        return jsonify(debug_data)
        
    except Exception as e:
        logger.error(f"❌ Error in debug endpoint: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Calendar-specific endpoints

@tasks_bp.route('/calendar/<user_id>/date/<date>', methods=['GET'])
@require_auth
def get_tasks_for_date(user_id, date):
    """Get all tasks for a specific date"""
    logger = get_logger()
    logger.info(f"📅 Getting tasks for user {user_id} on date: {date}")
    
    try:
        # Security: Ensure user can only access their own tasks
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s calendar")
            return jsonify({"error": "Unauthorized: Cannot access another user's calendar"}), 403
            
        # Validate date format
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
            
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        # Filter tasks for the specific date
        date_tasks = []
        for task in all_tasks:
            task_date = task.get('due_date')
            if task_date:
                try:
                    if isinstance(task_date, str):
                        task_dt = datetime.fromisoformat(task_date.replace('Z', '+00:00')).date()
                    else:
                        task_dt = task_date.date()
                    
                    if task_dt == target_date:
                        date_tasks.append(task)
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error for task {task.get('id')}: {e}")
                    continue
        
        logger.info(f"📅 Found {len(date_tasks)} tasks for date {date}")
        
        return jsonify({
            "date": date,
            "tasks": date_tasks,
            "count": len(date_tasks)
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting tasks for date: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/calendar/<user_id>/month/<year>/<month>', methods=['GET'])
@require_auth
def get_tasks_for_month(user_id, year, month):
    """Get all tasks for a specific month with calendar statistics"""
    logger = get_logger()
    logger.info(f"📅 Getting tasks for user {user_id} for month: {year}-{month}")
    
    try:
        # Security: Ensure user can only access their own tasks
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s calendar")
            return jsonify({"error": "Unauthorized: Cannot access another user's calendar"}), 403
            
        # Validate year and month
        try:
            year_int = int(year)
            month_int = int(month)
            if not (1 <= month_int <= 12):
                raise ValueError("Month must be between 1 and 12")
        except ValueError:
            return jsonify({"error": "Invalid year or month format"}), 400
            
        # Calculate date range for the month
        from calendar import monthrange
        start_date = datetime(year_int, month_int, 1)
        last_day = monthrange(year_int, month_int)[1]
        end_date = datetime(year_int, month_int, last_day, 23, 59, 59)
        
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        # Filter tasks for the month and organize by date
        month_tasks = []
        tasks_by_date = {}
        
        for task in all_tasks:
            task_date = task.get('due_date')
            if task_date:
                try:
                    if isinstance(task_date, str):
                        task_dt = datetime.fromisoformat(task_date.replace('Z', '+00:00'))
                    else:
                        task_dt = task_date
                    
                    if start_date <= task_dt <= end_date:
                        month_tasks.append(task)
                        date_key = task_dt.date().isoformat()
                        
                        if date_key not in tasks_by_date:
                            tasks_by_date[date_key] = []
                        tasks_by_date[date_key].append(task)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error for task {task.get('id')}: {e}")
                    continue
        
        # Calculate statistics
        total_tasks = len(month_tasks)
        completed_tasks = len([t for t in month_tasks if t.get('status') == 'completed'])
        pending_tasks = len([t for t in month_tasks if t.get('status') in ['pending', 'approved']])
        overdue_tasks = len([t for t in month_tasks if t.get('status') not in ['completed', 'cancelled'] and
                           datetime.fromisoformat(t['due_date'].replace('Z', '+00:00')) < datetime.now()])
        
        # Calculate days with tasks
        days_with_tasks = len(tasks_by_date)
        
        logger.info(f"📅 Found {total_tasks} tasks for {year}-{month} across {days_with_tasks} days")
        
        return jsonify({
            "year": year_int,
            "month": month_int,
            "month_name": start_date.strftime("%B"),
            "tasks": month_tasks,
            "tasks_by_date": tasks_by_date,
            "statistics": {
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "overdue_tasks": overdue_tasks,
                "days_with_tasks": days_with_tasks,
                "completion_rate": completed_tasks / total_tasks if total_tasks > 0 else 0.0
            },
            "period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting tasks for month: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/calendar/<user_id>/range', methods=['GET'])
@require_auth  
def get_tasks_for_date_range(user_id):
    """Get tasks for a custom date range (for calendar views)"""
    logger = get_logger()
    logger.info(f"📅 Getting tasks for user {user_id} with date range")
    
    try:
        # Security: Ensure user can only access their own tasks
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s calendar")
            return jsonify({"error": "Unauthorized: Cannot access another user's calendar"}), 403
            
        # Get query parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        group_by_date = request.args.get('group_by_date', 'true').lower() == 'true'
        
        if not start_date_str or not end_date_str:
            return jsonify({"error": "start_date and end_date parameters are required"}), 400
            
        try:
            start_date = datetime.fromisoformat(start_date_str)
            end_date = datetime.fromisoformat(end_date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD or ISO format"}), 400
            
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        # Filter tasks for the date range
        range_tasks = []
        tasks_by_date = {} if group_by_date else None
        
        for task in all_tasks:
            task_date = task.get('due_date')
            if task_date:
                try:
                    if isinstance(task_date, str):
                        task_dt = datetime.fromisoformat(task_date.replace('Z', '+00:00'))
                    else:
                        task_dt = task_date
                    
                    if start_date <= task_dt <= end_date:
                        range_tasks.append(task)
                        
                        if group_by_date:
                            date_key = task_dt.date().isoformat()
                            if date_key not in tasks_by_date:
                                tasks_by_date[date_key] = []
                            tasks_by_date[date_key].append(task)
                            
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error for task {task.get('id')}: {e}")
                    continue
        
        logger.info(f"📅 Found {len(range_tasks)} tasks for range {start_date_str} to {end_date_str}")
        
        response_data = {
            "start_date": start_date_str,
            "end_date": end_date_str,
            "tasks": range_tasks,
            "count": len(range_tasks)
        }
        
        if group_by_date:
            response_data["tasks_by_date"] = tasks_by_date
            response_data["days_with_tasks"] = len(tasks_by_date)
            
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"❌ Error getting tasks for date range: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/calendar/<user_id>/summary', methods=['GET'])
@require_auth
def get_calendar_summary(user_id):
    """Get calendar summary with upcoming tasks and statistics"""
    logger = get_logger()
    logger.info(f"📅 Getting calendar summary for user: {user_id}")
    
    try:
        # Security: Ensure user can only access their own tasks  
        if user_id != request.user_id:
            logger.warning(f"❌ Unauthorized access attempt: {request.user_id} tried to access {user_id}'s calendar")
            return jsonify({"error": "Unauthorized: Cannot access another user's calendar"}), 403
            
        firebase_service = current_app.firebase_service
        all_tasks = firebase_service.get_user_tasks(user_id)
        
        now = datetime.now()
        today = now.date()
        
        # Categorize tasks
        today_tasks = []
        upcoming_tasks = []
        overdue_tasks = []
        completed_today = []
        
        for task in all_tasks:
            task_date = task.get('due_date')
            if task_date:
                try:
                    if isinstance(task_date, str):
                        task_dt = datetime.fromisoformat(task_date.replace('Z', '+00:00'))
                    else:
                        task_dt = task_date
                    
                    task_date_only = task_dt.date()
                    
                    if task_date_only == today:
                        today_tasks.append(task)
                        if task.get('status') == 'completed':
                            completed_today.append(task)
                    elif task_date_only > today:
                        upcoming_tasks.append(task)
                    elif task.get('status') not in ['completed', 'cancelled']:
                        overdue_tasks.append(task)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Date parsing error for task {task.get('id')}: {e}")
                    continue
        
        # Sort upcoming tasks by date
        upcoming_tasks.sort(key=lambda t: t.get('due_date', ''))
        
        # Get next 7 days of tasks for quick preview
        next_week_tasks = []
        for i in range(1, 8):  # Next 7 days
            check_date = today + timedelta(days=i)
            day_tasks = [t for t in upcoming_tasks 
                        if datetime.fromisoformat(t['due_date'].replace('Z', '+00:00')).date() == check_date]
            if day_tasks:
                next_week_tasks.append({
                    "date": check_date.isoformat(),
                    "day_name": check_date.strftime("%A"),
                    "tasks": day_tasks,
                    "count": len(day_tasks)
                })
        
        summary = {
            "today": {
                "date": today.isoformat(),
                "tasks": today_tasks,
                "count": len(today_tasks),
                "completed_count": len(completed_today)
            },
            "upcoming": {
                "tasks": upcoming_tasks[:10],  # Limit to next 10 upcoming
                "total_count": len(upcoming_tasks)
            },
            "overdue": {
                "tasks": overdue_tasks,
                "count": len(overdue_tasks)
            },
            "next_week": next_week_tasks,
            "statistics": {
                "total_active_tasks": len(today_tasks) + len(upcoming_tasks) + len(overdue_tasks),
                "today_completion_rate": len(completed_today) / len(today_tasks) if today_tasks else 0.0,
                "overdue_count": len(overdue_tasks)
            }
        }
        
        logger.info(f"📅 Calendar summary: {len(today_tasks)} today, {len(upcoming_tasks)} upcoming, {len(overdue_tasks)} overdue")
        
        return jsonify(summary)
        
    except Exception as e:
        logger.error(f"❌ Error getting calendar summary: {str(e)}")
        return jsonify({"error": str(e)}), 500

@tasks_bp.route('/health', methods=['GET'])
def tasks_health_check():
    """Health check endpoint for task service"""
    logger = get_logger()
    start_time = time.time()
    
    try:
        firebase_service = current_app.firebase_service
        
        # Check Firebase connection
        firebase_healthy = firebase_service.health_check() if firebase_service else False
        
        # Check response time
        response_time = time.time() - start_time
        
        health_status = {
            "status": "healthy" if firebase_healthy else "degraded",
            "firebase_connection": firebase_healthy,
            "response_time_ms": round(response_time * 1000, 2),
            "timestamp": datetime.utcnow().isoformat(),
            "service": "tasks"
        }
        
        status_code = 200 if firebase_healthy else 503
        
        logger.info(f"🏥 Health check completed: {health_status['status']} in {response_time:.3f}s")
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
            "service": "tasks"
        }), 500