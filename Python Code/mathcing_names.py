import pandas as pd
from collections import Counter

# Load the 4 files
file1 = pd.read_csv('SC_Monthly_Full_File.csv')
file2 = pd.read_csv('CAPPEX_DB.DBT.B_CPX_REFERENCE_DATA_HIGH_SCHOOL.csv')
file3 = pd.read_excel('HS Ceeb Code file_PAPA.xlsx', engine='openpyxl')
file4 = pd.read_csv('CROSS_TENANT_DB.COMMON.REF__HIGH_SCHOOLS.csv')

# Convert all column names to lowercase
file1.columns = file1.columns.str.lower()
file2.columns = file2.columns.str.lower()
file3.columns = file3.columns.str.lower()
file4.columns = file4.columns.str.lower()

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
    'hs_name': 'school_name'
}

file1 = file1.rename(columns=rename_dict)
file2 = file2.rename(columns=rename_dict)
file3 = file3.rename(columns=rename_dict)
file4 = file4.rename(columns=rename_dict)


def standardize_ceeb_code(df, col_name='hs_ceeb_code'):
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
        df[col_name] = df[col_name].apply(
            lambda x: x.zfill(6) if pd.notna(x) else x
        )
    return df


def normalize_school_name(name):
    if pd.isna(name):
        return pd.NA
    name = str(name).strip()
    if not name:
        return pd.NA
    return name.title()


def add_prefix(df, prefix, key='hs_ceeb_code'):
    return df.rename(columns={
        col: f'{prefix}{col}' for col in df.columns if col != key
    })


def get_best_school_name(school_names):
    """
    Select best school name using:
    1. Most frequent value
    2. Tie-breaker based on cleanliness
    """
    names = [
        str(n).strip()
        for n in school_names
        if pd.notna(n) and str(n).strip()
    ]

    if not names:
        return None

    name_counts = Counter(names)
    max_count = max(name_counts.values())

    # Get all names tied for highest frequency
    top_names = [name for name, count in name_counts.items() if count == max_count]

    # Clear winner
    if len(top_names) == 1:
        return top_names[0]

    # Tie-breaker: cleaner / more standard-looking value wins
    def score_name(name):
        length_score = len(name) / 100
        abbrev_penalty = -name.count('.') * 10
        dash_penalty = -name.count('-') * 2
        return length_score + abbrev_penalty + dash_penalty

    return max(top_names, key=score_name)


# Standardize CEEB codes
file1 = standardize_ceeb_code(file1)
file2 = standardize_ceeb_code(file2)
file3 = standardize_ceeb_code(file3)
file4 = standardize_ceeb_code(file4)

# Normalize school_name column in each file, if present
for df in [file1, file2, file3, file4]:
    if 'school_name' in df.columns:
        df['school_name'] = df['school_name'].apply(normalize_school_name)

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

# Merge files on hs_ceeb_code
merged_df = file1.merge(file2, on='hs_ceeb_code', how='outer')
merged_df = merged_df.merge(file3, on='hs_ceeb_code', how='outer')
merged_df = merged_df.merge(file4, on='hs_ceeb_code', how='outer')

print(f"\nMerged shape: {merged_df.shape}")
print(f"Merged columns: {merged_df.columns.tolist()}")

# Explicit source-specific school name columns
school_name_cols = [
    col for col in [
        'SC_school_name',
        'CAPPEX_school_name',
        'PAPA_school_name',
        'Enroll360_school_name'
    ]
    if col in merged_df.columns
]

print(f"\nSchool name columns: {school_name_cols}")

# Create best_school_name from the source columns
merged_df['best_school_name'] = merged_df[school_name_cols].apply(
    lambda row: get_best_school_name(row),
    axis=1
)

# Final output columns
final_columns = ['hs_ceeb_code'] + school_name_cols + ['best_school_name']
result_df = merged_df[final_columns]

# Save outputs
result_df.to_csv('/Users/RSanghavi/Snowflake/Python Code/merged_schools.csv', index=False)
result_df.to_excel('/Users/RSanghavi/Snowflake/Python Code/merged_schools.xlsx', index=False, engine='openpyxl')

print(f"\n✓ Merged {len(result_df)} rows")
print("\nFirst 10 rows:")
print(result_df.head(10))