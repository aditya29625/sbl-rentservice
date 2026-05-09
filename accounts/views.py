from django.shortcuts import render

# Create your views here.
from datetime import date

start_date = date(2025, 5, 15)
current_date = date.today()

calculated_months = (current_date.year - start_date.year) * 12 + (current_date.month - start_date.month)

print(calculated_months)
