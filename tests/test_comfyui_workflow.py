import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / "workflows" / "minimax_h3_prototype.workflow.json"


class ComfyUIWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
        cls.nodes = {node["id"]: node for node in cls.data["nodes"]}
        cls.links = {link[0]: link for link in cls.data["links"]}

    def test_workflow_envelope(self):
        self.assertEqual(self.data["version"], 0.4)
        self.assertEqual(self.data["last_node_id"], max(self.nodes))
        self.assertEqual(self.data["last_link_id"], max(self.links))

    def test_node_ids_and_link_ids_are_unique(self):
        self.assertEqual(len(self.nodes), len(self.data["nodes"]))
        self.assertEqual(len(self.links), len(self.data["links"]))

    def test_every_link_references_existing_nodes(self):
        for link_id, origin_id, origin_slot, target_id, target_slot, _ in self.data["links"]:
            self.assertIn(origin_id, self.nodes, link_id)
            self.assertIn(target_id, self.nodes, link_id)
            self.assertLess(origin_slot, len(self.nodes[origin_id]["outputs"]))
            self.assertLess(target_slot, len(self.nodes[target_id]["inputs"]))

    def test_socket_link_references_exist_and_match(self):
        for node in self.nodes.values():
            for slot, output in enumerate(node.get("outputs", [])):
                for link_id in output.get("links") or []:
                    link = self.links[link_id]
                    self.assertEqual((link[1], link[2]), (node["id"], slot))
            for slot, input_socket in enumerate(node.get("inputs", [])):
                link_id = input_socket.get("link")
                if link_id is not None:
                    link = self.links[link_id]
                    self.assertEqual((link[3], link[4]), (node["id"], slot))

    def test_required_prototype_nodes_exist(self):
        names = {node["properties"]["Node name for S&R"] for node in self.nodes.values()}
        required = {
            "RealisticStyle",
            "GuomanStyle",
            "Cinematic3DStyle",
            "PromptCompilerPlaceholder",
            "MiniMaxH3SegmentAPlaceholder",
            "ContinuityCheckpointA",
            "MiniMaxH3SegmentBPlaceholder",
            "QualityGatePlaceholder",
            "ConcatMP4Placeholder",
            "SaveMasterPlaceholder",
            "GifPreviewPlaceholder",
            "Move35HardGate",
        }
        self.assertTrue(required <= names)

    def test_no_secret_is_embedded(self):
        serialized = json.dumps(self.data, ensure_ascii=False).lower()
        self.assertNotIn("bearer ", serialized)
        self.assertNotRegex(serialized, r'"api[_ -]?key"\s*:\s*"[^"$]{8,}"')
        self.assertIn("minimax_api_key", serialized)


if __name__ == "__main__":
    unittest.main()
