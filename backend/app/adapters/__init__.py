from .mock_push import MockPushAdapter
from .mock_notify import MockNotifyAdapter
from .local_auth import LocalAuthAdapter
from .mock_scheduler import MockSchedulerAdapter

push_adapter = MockPushAdapter(fail_rate=0.1)
notify_adapter = MockNotifyAdapter()
scheduler_adapter = MockSchedulerAdapter()