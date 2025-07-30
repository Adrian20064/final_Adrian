from django import forms

class TripForm(forms.Form):
    start_city = forms.ChoiceField(label="Start City")
    end_city = forms.ChoiceField(label="End City")

    def __init__(self, *args, **kwargs):
        cities = kwargs.pop('cities', [])
        super().__init__(*args, **kwargs)

        city_choices = [(city["name"], city["name"]) for city in cities]
        self.fields['start_city'].choices = city_choices
        self.fields['end_city'].choices = city_choices
