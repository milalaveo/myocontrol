SELECT '| ' || c.table_name || ' | ' || c.column_name || ' | ' ||
       replace(c.udt_name, '|', '\|') || ' | ' || c.is_nullable || ' | ' ||
       replace(COALESCE(c.column_default, ''), '|', '\|') || ' |'
FROM information_schema.columns c
JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name
WHERE c.table_schema = 'myoprosthesis' AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position;
