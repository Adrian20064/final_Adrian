from django import forms

class TravelForm(forms.Form):
    start_city = forms.CharField(label='Start City', max_length=100)
    end_city = forms.CharField(label='End City', max_length=100)
