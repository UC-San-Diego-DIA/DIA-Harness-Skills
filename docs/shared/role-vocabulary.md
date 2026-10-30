# Sheet role vocabulary

`$dia-tableau-dashboard-docs` validates every proposed sheet role against this controlled vocabulary. A proposal outside this list is a bug, not a prompt option.

| Role | Definition |
| --- | --- |
| `kpi_card` | A sheet presenting one headline value with little or no axes or detail. |
| `trend_chart` | A sheet showing how a measure changes over time. |
| `breakdown_chart` | A sheet splitting a measure across categories or dimensions. |
| `distribution_chart` | A sheet showing how a measure's values spread across a range. |
| `table` | A sheet presenting rows of field values for direct reading. |
| `text_annotation` | A sheet presenting explanatory text rather than data marks. |
| `data_date_stamp` | A sheet stating the date through which the data is current. |
| `map` | A sheet plotting measures on a geographic canvas. |
| `filter_panel` | A sheet acting primarily as a control surface for other sheets. |
| `other` | A sheet whose function fits none of the roles above. |

## Field semantic types (reserved for future use)

| Type | Definition |
| --- | --- |
| `dimension` | A field used to group or slice records. |
| `measure` | A field carrying an aggregated numeric value. |
| `temporal` | A field carrying a date or time value used along an axis or filter. |
| `ordinal` | A field with a meaningful sort order but uneven spacing. |
| `nominal` | A field with unordered category values. |
| `geo` | A field interpreted as a geographic location. |
| `key` | A field identifying records rather than describing them. |
