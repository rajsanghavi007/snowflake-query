import pandas as pd
import re
from rapidfuzz import fuzz

ceeb_dtype = {
    'hs_ceeb_code': str,
    'ceeb_cd': str,
    'ceeb_code': str,
    'ceeb': str,
    'hs_ceeb': str
}

file1 = pd.read_csv('final_addr2.csv', dtype=ceeb_dtype)
file2 = pd.read_csv('CAPPEX_DB.DBT.B_CPX_REFERENCE_DATA_HIGH_SCHOOL.csv', dtype=ceeb_dtype)
file3 = pd.read_excel('HS Ceeb Code file_PAPA.xlsx', dtype=ceeb_dtype, engine='openpyxl')
file4 = pd.read_csv('CROSS_TENANT_DB.COMMON.REF__HIGH_SCHOOLS.csv', dtype=ceeb_dtype)

# Convert all column names to lowercase
for df in [file1, file2, file3, file4]:
    df.columns = df.columns.str.lower()

# Standardize key columns
rename_dict = {
    # CEEB code mappings
    'hs_ceeb_code': 'hs_ceeb_code',
    'ceeb_cd': 'hs_ceeb_code',
    'ceeb_code': 'hs_ceeb_code',
    'ceeb': 'hs_ceeb_code',
    'hs_ceeb': 'hs_ceeb_code',

    # School name mappings
    'school_name': 'school_name',
    'name': 'school_name',
    'hs_name': 'school_name',

    # Address1 mappings
    'address1': 'address1',
    'addr1': 'address1',
    'address_line_1': 'address1',

    # Address2 mappings
    'address2': 'address2',
    'addr2': 'address2',
    'address_line_2': 'address2',

    # City mappings
    'city': 'city',

    # State mappings
    'state': 'state',

    # Zip mappings
    'zip': 'zip',
    'zip_code': 'zip',
    'zip5': 'zip',

    # Country mappings
    'country': 'country'
}

file1 = file1.rename(columns=rename_dict)
file2 = file2.rename(columns=rename_dict)
file3 = file3.rename(columns=rename_dict)
file4 = file4.rename(columns=rename_dict)


def standardize_ceeb_code(df, col_name='hs_ceeb_code'):
    """
    Keep ceeb code as-is after trimming and removing trailing .0
    No zero-fill padding.
    Example:
      88 -> 88
      000088 -> 000088
    """
    if col_name in df.columns:
        df[col_name] = (
            df[col_name]
            .astype(str)
            .str.strip()
            .str.replace(r'\.0$', '', regex=True)
        )

        df[col_name] = df[col_name].replace({
            'nan': pd.NA,
            'None': pd.NA,
            '': pd.NA
        })

    return df


def normalize_school_name(name):
    if pd.isna(name):
        return pd.NA
    name = str(name).strip()
    if not name:
        return pd.NA
    return name.title()


def normalize_text(val):
    if pd.isna(val):
        return pd.NA
    val = str(val).strip()
    if not val:
        return pd.NA
    return val.title()


def normalize_zip(val):
    if pd.isna(val):
        return pd.NA
    val = str(val).strip().replace('.0', '')
    if not val:
        return pd.NA
    return val


def add_prefix(df, prefix, key='hs_ceeb_code'):
    return df.rename(columns={
        col: f'{prefix}{col}' for col in df.columns if col != key
    })


def first_non_null_by_priority(row, cols):
    for col in cols:
        if col in row.index and pd.notna(row[col]) and str(row[col]).strip():
            return str(row[col]).strip()
    return None


SOURCE_PRIORITY = {
    'SC': 1,          # final_addr2
    'Enroll360': 2,   # CROSS TENANT
    'CAPPEX': 3,
    'PAPA': 4
}


def source_from_col(col_name):
    if col_name.startswith('SC_'):
        return 'SC'
    if col_name.startswith('Enroll360_'):
        return 'Enroll360'
    if col_name.startswith('CAPPEX_'):
        return 'CAPPEX'
    if col_name.startswith('PAPA_'):
        return 'PAPA'
    return 'ZZZ'


def clean_name_for_match(name):
    """
    Basic cleanup only for fuzzy matching.
    No custom replacements like HS -> HIGH SCHOOL, SAINT -> ST, etc.
    """
    if pd.isna(name):
        return None

    name = str(name).strip().upper()
    if not name:
        return None

    name = re.sub(r'&', ' AND ', name)
    name = re.sub(r'[^A-Z0-9\s]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def is_abbreviation(name):
    if pd.isna(name):
        return False

    name = str(name).strip()
    if not name:
        return False

    letters_only = re.sub(r'[^A-Za-z]', '', name)

    if 1 <= len(letters_only) <= 5:
        return True

    if name.count('.') >= 2:
        return True

    tokens = re.findall(r'[A-Za-z]+', name)
    if tokens and sum(len(t) <= 2 for t in tokens) / len(tokens) >= 0.6:
        return True

    return False


def build_name_clusters(entries, threshold=90):
    clusters = []

    for entry in entries:
        placed = False

        for cluster in clusters:
            scores = [
                fuzz.token_set_ratio(entry['cleaned_name'], member['cleaned_name'])
                for member in cluster
            ]
            if max(scores) >= threshold:
                cluster.append(entry)
                placed = True
                break

        if not placed:
            clusters.append([entry])

    return clusters


def choose_best_name_from_cluster(cluster):
    """
    Rule:
    - If any value in the cluster is abbreviated, use ONLY source priority
    - Otherwise use source priority, then prefer fuller name
    """
    has_abbrev = any(is_abbreviation(e['original_name']) for e in cluster)

    if has_abbrev:
        best_entry = sorted(
            cluster,
            key=lambda e: SOURCE_PRIORITY.get(e['source'], 999)
        )[0]
        return best_entry['original_name']

    best_entry = sorted(
        cluster,
        key=lambda e: (
            SOURCE_PRIORITY.get(e['source'], 999),
            -len(e['original_name'])
        )
    )[0]
    return best_entry['original_name']


def get_best_school_name_rapidfuzz(row, school_name_cols, threshold=90):
    entries = []

    for col in school_name_cols:
        val = row.get(col, pd.NA)
        if pd.notna(val) and str(val).strip():
            entries.append({
                'original_name': str(val).strip(),
                'cleaned_name': clean_name_for_match(val),
                'source': source_from_col(col)
            })

    if not entries:
        return None

    valid_cleaned = [e['cleaned_name'] for e in entries if e['cleaned_name']]
    if not valid_cleaned:
        return None

    clusters = build_name_clusters(entries, threshold=threshold)

    # Pick best cluster by:
    # 1. most agreement
    # 2. best source present
    # 3. fuller name support
    clusters = sorted(
        clusters,
        key=lambda c: (
            len(c),
            -min(SOURCE_PRIORITY.get(x['source'], 999) for x in c),
            max(len(x['original_name']) for x in c)
        ),
        reverse=True
    )

    winning_cluster = clusters[0]
    return choose_best_name_from_cluster(winning_cluster)


# Standardize CEEB codes
file1 = standardize_ceeb_code(file1)
file2 = standardize_ceeb_code(file2)
file3 = standardize_ceeb_code(file3)
file4 = standardize_ceeb_code(file4)

# Normalize fields in each file
for df in [file1, file2, file3, file4]:
    if 'school_name' in df.columns:
        df['school_name'] = df['school_name'].apply(normalize_school_name)
    if 'address1' in df.columns:
        df['address1'] = df['address1'].apply(normalize_text)
    if 'address2' in df.columns:
        df['address2'] = df['address2'].apply(normalize_text)
    if 'city' in df.columns:
        df['city'] = df['city'].apply(normalize_text)
    if 'state' in df.columns:
        df['state'] = df['state'].apply(normalize_text)
    if 'zip' in df.columns:
        df['zip'] = df['zip'].apply(normalize_zip)
    if 'country' in df.columns:
        df['country'] = df['country'].apply(normalize_text)

print("CEEB code dtypes:")
print(file1['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file1.columns else 'missing')
print(file2['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file2.columns else 'missing')
print(file3['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file3.columns else 'missing')
print(file4['hs_ceeb_code'].dtype if 'hs_ceeb_code' in file4.columns else 'missing')

# Add source prefixes so lineage is clear after merge
file1 = add_prefix(file1, 'SC_')
file2 = add_prefix(file2, 'CAPPEX_')
file3 = add_prefix(file3, 'PAPA_')
file4 = add_prefix(file4, 'Enroll360_')

# Merge files on hs_ceeb_code directly
merged_df = file1.merge(file2, on='hs_ceeb_code', how='outer')
merged_df = merged_df.merge(file3, on='hs_ceeb_code', how='outer')
merged_df = merged_df.merge(file4, on='hs_ceeb_code', how='outer')

print(f"\nMerged shape: {merged_df.shape}")
print(f"Merged columns: {merged_df.columns.tolist()}")

# Explicit source-specific school name columns
school_name_cols = [
    col for col in [
        'SC_school_name',
        'Enroll360_school_name',
        'CAPPEX_school_name',
        'PAPA_school_name'
    ]
    if col in merged_df.columns
]

print(f"\nSchool name columns: {school_name_cols}")

# Create best_school_name using RapidFuzz
merged_df['best_school_name'] = merged_df.apply(
    lambda row: get_best_school_name_rapidfuzz(
        row,
        school_name_cols=school_name_cols,
        threshold=90
    ),
    axis=1
)

# Priority: SC -> Enroll360 -> CAPPEX -> PAPA
address1_cols = [
    col for col in [
        'SC_address1',
        'Enroll360_address1',
        'CAPPEX_address1',
        'PAPA_address1'
    ]
    if col in merged_df.columns
]

address2_cols = [
    col for col in [
        'SC_address2',
        'Enroll360_address2',
        'CAPPEX_address2',
        'PAPA_address2'
    ]
    if col in merged_df.columns
]

city_cols = [
    col for col in [
        'SC_city',
        'Enroll360_city',
        'CAPPEX_city',
        'PAPA_city'
    ]
    if col in merged_df.columns
]

state_cols = [
    col for col in [
        'SC_state',
        'Enroll360_state',
        'CAPPEX_state',
        'PAPA_state'
    ]
    if col in merged_df.columns
]

zip_cols = [
    col for col in [
        'SC_zip',
        'Enroll360_zip',
        'CAPPEX_zip',
        'PAPA_zip'
    ]
    if col in merged_df.columns
]

country_cols = [
    col for col in [
        'SC_country',
        'Enroll360_country',
        'CAPPEX_country',
        'PAPA_country'
    ]
    if col in merged_df.columns
]

# Create final address fields
merged_df['address1'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, address1_cols),
    axis=1
)

merged_df['address2'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, address2_cols),
    axis=1
)

merged_df['city'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, city_cols),
    axis=1
)

merged_df['state'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, state_cols),
    axis=1
)

merged_df['zip'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, zip_cols),
    axis=1
)

merged_df['country'] = merged_df.apply(
    lambda row: first_non_null_by_priority(row, country_cols),
    axis=1
)

# Final output columns
final_columns = (
    ['hs_ceeb_code']
    + school_name_cols
    + ['best_school_name', 'address1', 'address2', 'city', 'state', 'zip', 'country']
)

result_df = merged_df[final_columns].copy()

# Force state and country to uppercase in final output
result_df['state'] = result_df['state'].apply(lambda x: x.upper() if pd.notna(x) else x)
result_df['country'] = result_df['country'].apply(lambda x: x.upper() if pd.notna(x) else x)

# Save outputs
result_df.to_csv('merged_schools_new_1_12.csv', index=False)
result_df.to_excel('merged_schools_new_1_12.xlsx', index=False, engine='openpyxl')

print(f"\nMerged {len(result_df)} rows")
print("\nFirst 10 rows:")
print(result_df.head(10))