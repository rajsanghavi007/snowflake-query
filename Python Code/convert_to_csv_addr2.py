import pandas as pd

input_file = "/Users/RSanghavi/Snowflake/Python Code/202603_SC_Monthly_Full_File.txt"
output_csv = "/Users/RSanghavi/Snowflake/Python Code/final_addr2.csv"


def cut(text, start, length=None):
    """Extract substring from fixed-width text."""
    if length is None:
        return text[start:].rstrip("\n").rstrip()
    return text[start:start + length].rstrip()


def detect_us(line):
    """Detect if line is US format."""
    state_candidate = cut(line, 386, 2).strip()
    country_candidate = cut(line, 439, 2).strip()
    return len(state_candidate) == 2 and state_candidate.isalpha() and country_candidate == "US"


def parse_us(line):
    """Parse US format: 6, 50, 100, 180, 50, 2, 51, remaining"""
    hs_ceeb_code = cut(line, 0, 6)
    school_name = cut(line, 6, 50)

    address1 = cut(line, 56, 100)
    address2 = cut(line, 156, 180)
    address3 = ""

    city = cut(line, 336, 50)
    state = cut(line, 386, 2)
    zip_code = cut(line, 388, 51)
    rest = cut(line, 439, None)

    rest_parts = rest.split()
    country = rest_parts[0] if len(rest_parts) > 0 else ""
    school_type = rest_parts[1] if len(rest_parts) > 1 else ""

    return {
        "hs_ceeb_code": hs_ceeb_code.strip().zfill(6),
        "school_name": school_name.strip(),
        "address1": address1.strip(),
        "address2": address2.strip(),
        "address3": address3.strip(),
        "city": city.strip(),
        "state": state.strip(),
        "zip_code": zip_code.strip(),
        "country": country.strip(),
        "school_type": school_type.strip()
    }


def parse_intl(line):
    """Parse International format: 6, 50, 100, 80, 100, 61, 32, 10, 11"""
    hs_ceeb_code = cut(line, 0, 6)
    school_name = cut(line, 6, 50)

    address1 = cut(line, 56, 100)
    address2 = cut(line, 156, 80)
    address3 = cut(line, 236, 100)

    city = cut(line, 336, 61)
    state = cut(line, 397, 32)
    zip_code = cut(line, 429, 10)
    country_type = cut(line, 439, 11)

    parts = country_type.split()
    country = parts[0] if len(parts) > 0 else ""
    school_type = parts[1] if len(parts) > 1 else ""

    return {
        "hs_ceeb_code": hs_ceeb_code.strip().zfill(6),
        "school_name": school_name.strip(),
        "address1": address1.strip(),
        "address2": address2.strip(),
        "address3": address3.strip(),
        "city": city.strip(),
        "state": state.strip(),
        "zip_code": zip_code.strip(),
        "country": country.strip(),
        "school_type": school_type.strip()
    }


rows = []

with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
    for raw_line in f:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue

        if detect_us(line):
            row = parse_us(line)
        else:
            row = parse_intl(line)

        rows.append(row)

df = pd.DataFrame(rows)

# Clean whitespace
for col in df.columns:
    df[col] = df[col].astype(str).str.strip()

# Preserve leading zeros
df["hs_ceeb_code"] = df["hs_ceeb_code"].str.zfill(6)

# Keep zip as text
df["zip_code"] = df["zip_code"].astype(str).str.strip()

# Merge address2 and address3 into final address2
df["address2"] = df.apply(
    lambda x: ", ".join(
        [part for part in [x["address2"], x["address3"]] if part and part.strip()]
    ),
    axis=1
)

# Drop address3 after merge
df = df.drop(columns=["address3"])



# Save output
df.to_csv("/Users/RSanghavi/Snowflake/Python Code/final_addr2.csv", index=False)

print(df.head(20).to_string(index=False))
print(f"\n✓ Total rows: {len(df)}")

