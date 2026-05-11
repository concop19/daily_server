# test_datastore2.py
import sys
sys.path.insert(0, r"D:\dream_project\daily_mate_code\demo_server")
import data_store

data_store.load_all()

# Check real IDs
dishes = data_store.get_all_dishes()
print("First dish ID:", dishes[0].get("id"), "keys:", list(dishes[0].keys())[:8])
print("Dish ID (type):", type(dishes[0].get("id")))

# Test by real ID
real_id = dishes[0].get("id")
dish = data_store.get_dish_by_id(real_id)
print("Dish found by id:", dish is not None)

# Test ingredient for dish
ings = data_store.get_ingredients_for_dish(real_id)
print("Dish ingredients:", len(ings))

# Test advice templates - check what context_types exist
tmpl_all = data_store.get_all_advice_templates()
if tmpl_all:
    print("Template keys:", list(tmpl_all[0].keys()))
    print("Sample context_type:", tmpl_all[0].get("context_type"), "trigger_dim:", tmpl_all[0].get("trigger_dim"))
