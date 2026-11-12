import unittest

from src.pipeline.complete_community_scenarios import complete_rows


class MissingEpriCoverageTests(unittest.TestCase):
    def test_missing_epri_sites_keep_population_and_basin_context(self):
        fields=['site_id','epri_scenario','aqueduct_scenario','pfaf_id','pop_5km',
                'annual_water_footprint_m3','water_status','ws_x_s','ws_x_c']
        rows=[dict(site_id='known',epri_scenario=d,aqueduct_scenario=c)
              for d in ['low','moderate','high','higher']
              for c in ['optimistic','bau','pessimistic']]
        exposure=[dict(site_id='missing',pop_5km='123')]
        mapping=[dict(site_id='missing',pfaf_id='111111')]
        future=[dict(pfaf_id='111111',aqueduct_scenario=c,ws_x_s='4',ws_x_c='3')
                for c in ['optimistic','bau','pessimistic']]
        water=[dict(site_id='missing',annual_water_footprint_m3='',water_status='no_epri_growth')]
        result,added=complete_rows(rows,fields,exposure,mapping,future,water)
        self.assertEqual(added,['missing'])
        self.assertEqual(len(result),24)
        missing=[r for r in result if r['site_id']=='missing']
        self.assertTrue(all(r['pop_5km']=='123' for r in missing))
        self.assertTrue(all(r['water_status']=='no_epri_growth' for r in missing))
        self.assertTrue(all(r['annual_water_footprint_m3']=='' for r in missing))
        self.assertTrue(all(r['high_water_stress']=='True' for r in missing))
        again,added_again=complete_rows(result,fields,exposure,mapping,future,water)
        self.assertEqual(len(again),24)
        self.assertEqual(added_again,[])


if __name__=='__main__':
    unittest.main()
