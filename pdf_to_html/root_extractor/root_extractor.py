import json
import sys
import os
import pprint # For pretty printing the resulting structure

def rebuild_structure_without_content(data):
    """
    Recursively rebuilds the data structure (dicts and lists) from the input,
    omitting any key-value pair where the key is 'content'.

    Args:
        data: The Python dictionary, list, or primitive value to process.

    Returns:
        A new data structure (dict, list, or primitive) with 'content' keys removed,
        or None if the input itself should be removed (e.g., a dict becoming empty).
    """
    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            # *** Skip the 'content' key ***
            if key == "content":
                continue

            # Recursively process the value
            processed_value = rebuild_structure_without_content(value)

            # Only add the key-value pair if the processed value is not None
            # (This handles cases where a nested dict/list might become empty after filtering)
            # Although for this specific request, we might want to keep empty structures
            # Let's keep the key even if the processed value is an empty dict/list
            new_dict[key] = processed_value

        # Return the new dictionary, even if empty
        return new_dict

    elif isinstance(data, list):
        new_list = []
        for item in data:
            processed_item = rebuild_structure_without_content(item)
            # Add the processed item to the list
            new_list.append(processed_item)
        return new_list

    else:
        # Primitive types (str, int, float, bool, None) are returned as is
        return data

def display_values_without_content(json_filepath):
    """
    Loads a JSON file, reconstructs its data excluding 'content' keys,
    and prints the resulting structure with values.

    Args:
        json_filepath: Path to the JSON file.
    """
    if not os.path.exists(json_filepath):
        print(f"Error: File not found at '{json_filepath}'")
        return

    try:
        with open(json_filepath, 'r', encoding='utf-8') as f:
            original_data = json.load(f)

        # Rebuild the data structure, filtering out 'content' keys
        filtered_data = rebuild_structure_without_content(original_data)

        print(f"Data values for '{json_filepath}' (excluding 'content' keys/values):")
        print("-" * 60)
        # Use pprint to display the potentially complex nested structure clearly
        pprint.pprint(filtered_data, indent=2)
        print("-" * 60)


    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from '{json_filepath}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


# --- Example Usage ---
if __name__ == "__main__":
    # Replace with the actual path to your JSON file
    file_path = "bewastha_jagaune_ain.json"

    # Or get filename from command line argument
    # if len(sys.argv) > 1:
    #     file_path = sys.argv[1]
    # else:
    #     print("Usage: python script_name.py <path_to_json_file>")
    #     sys.exit(1)

    display_values_without_content(file_path)