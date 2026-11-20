"""Temporal supplies durable check-in ticks; SQL receipts arbitrate every effect."""

from datetime import timedelta

from temporalio import activity, workflow
from temporalio.common import RetryPolicy


@workflow.defn
class CallCheckIns:
    def __init__(self):
        self.woken = False

    @workflow.signal
    def wake(self):
        self.woken = True

    @workflow.run
    async def run(self):
        for _ in range(240):
            await workflow.execute_activity(
                "yggdras_call_sweep",
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            try:
                await workflow.wait_condition(lambda: self.woken, timeout=timedelta(seconds=15))
            except TimeoutError:
                pass
            self.woken = False
        workflow.continue_as_new()


class CallActivities:
    def __init__(self, service):
        self.service = service

    @activity.defn(name="yggdras_call_sweep")
    def sweep(self):
        self.service.tick()
