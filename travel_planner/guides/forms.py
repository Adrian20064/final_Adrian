from django import forms

class TravelForm(forms.Form):
    start_city = forms.ChoiceField(choices=[])  # choices vacíos por defecto
    end_city = forms.ChoiceField(choices=[])

    def __init__(self, *args, **kwargs):
        cities = kwargs.pop('cities', [])  # obtener las ciudades
        super().__init__(*args, **kwargs)
        city_choices = [(city, city) for city in cities]
        self.fields['start_city'].choices = city_choices
        self.fields['end_city'].choices = city_choices
