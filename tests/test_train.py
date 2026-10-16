import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from train import parse,features
class Tests(unittest.TestCase):
 def test_parse(self):
  rows=parse('Pick 3 Morning,10,15,2026,1,0,4,5\nPick 3 Morning,10,14,2026,2,2,2,1\n','morning')
  self.assertEqual(rows[0][1],(2,2,2));self.assertEqual(rows[1][1],(1,0,4))
 def test_features(self):
  self.assertEqual(len(features([(1,2,3)]*40)),107)
if __name__=='__main__':unittest.main()
