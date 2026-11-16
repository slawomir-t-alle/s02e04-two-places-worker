import json
import os
import unittest
from unittest.mock import patch

import worker


class WorkerFlowTest(unittest.TestCase):
    def test_submit_keeps_notes_separate_and_passes_latest_step(self):
        notes = ["tram-3 stalled @0:12", "tram-3 reset @0:31"]
        calls = []

        def fake_tool(name, arguments):
            calls.append((name, arguments))
            if name == "transcribe":
                return {"step": "step-1", "segments": []}
            if name == "memo_write":
                return {"step": f"step-{len(calls)}"}
            if name == "memo_search":
                return {"step": "step-4", "notes": notes}
            return {"status": "accepted", "receipt": "receipt", "result": arguments["result"]}

        with patch.dict(os.environ, {"MODE": "submit", "NOTES_JSON": json.dumps(notes)}), patch.object(worker, "tool", fake_tool):
            result = worker.run()
        self.assertEqual([name for name, _ in calls], ["transcribe", "memo_write", "memo_write", "memo_search", "submit"])
        self.assertEqual(calls[-1][1]["step"], "step-4")
        self.assertEqual(result["submission"]["result"], "\n".join(notes))


if __name__ == "__main__":
    unittest.main()
