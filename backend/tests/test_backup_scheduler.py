from app import backup_scheduler


def test_backup_scheduler_registers_one_daily_utc_job(monkeypatch):
    registered = {}

    class FakeScheduler:
        running = False

        def add_job(self, function, trigger, **kwargs):
            registered.update(function=function, trigger=trigger, **kwargs)

        def start(self):
            self.running = True

    fake = FakeScheduler()
    monkeypatch.setattr(backup_scheduler, "_scheduler", fake)
    backup_scheduler.start_backup_scheduler()
    backup_scheduler.start_backup_scheduler()

    assert registered["id"] == "fittrack-daily-backup"
    assert registered["max_instances"] == 1
    assert registered["coalesce"] is True
    assert fake.running is True
