import json
import subprocess
import unittest
from importlib.resources import files


class RoutePlannerTests(unittest.TestCase):
    @staticmethod
    def run_node(expression: str):
        planner = files("botw_companion.web").joinpath("route_planner.js")
        script = f"const p=require({json.dumps(str(planner))});console.log(JSON.stringify({expression}));"
        result = subprocess.run(["node", "-e", script], check=True, text=True,
                                capture_output=True)
        return json.loads(result.stdout)

    def test_nearest_neighbor_and_two_opt_remove_detours(self):
        value = self.run_node("(()=>{const a=[{id:'a',x:30,z:0},{id:'b',x:10,z:0},{id:'c',x:20,z:0}];const r=p.optimize(a,{x:0,z:0});return {ids:r.map(x=>x.id),distance:p.routeDistance(r,{x:0,z:0})}})()")
        self.assertEqual(value, {"ids": ["b", "c", "a"], "distance": 30})

    def test_locked_step_keeps_its_position(self):
        value = self.run_node("(()=>{const a=[{id:'a',x:30,z:0},{id:'b',x:10,z:0,locked:true},{id:'c',x:20,z:0}];return p.optimize(a,{x:0,z:0}).map(x=>x.id)})()")
        self.assertEqual(value[1], "b")

    def test_legs_expose_segment_and_cumulative_distances(self):
        value = self.run_node("p.legs([{x:3,z:4},{x:6,z:8}],{x:0,z:0}).map(x=>[x.distance,x.cumulative])")
        self.assertEqual(value, [[5, 5], [5, 10]])

    def test_region_strategy_reduces_region_changes(self):
        value = self.run_node("(()=>{const a=[{id:'a',x:10,z:0,region:'A'},{id:'b',x:11,z:0,region:'B'},{id:'c',x:20,z:0,region:'A'}];return p.optimize(a,{x:0,z:0,region:'A'},'region').map(x=>x.id)})()")
        self.assertEqual(value, ["a", "c", "b"])

    def test_teleport_strategy_recognizes_towers_and_shrines(self):
        value = self.run_node("p.travelCost({x:0,z:0},{x:100,z:0,categorie:'tours'},'teleport')")
        self.assertEqual(value, 35)


if __name__ == "__main__":
    unittest.main()