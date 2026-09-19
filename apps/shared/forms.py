from django import forms


class FormControlMixin:
    """
    Applies consistent Tailwind classes to every widget in the form.
    Inherit from this before ModelForm/Form to get styled fields
    without touching individual widget definitions.

    Usage:
        class MyForm(FormControlMixin, forms.ModelForm):
            ...
    """

    #: Base classes applied to all text-like inputs
    INPUT_CLASSES = 'field'
    SELECT_CLASSES = 'field'
    TEXTAREA_CLASSES = 'field resize-none'
    CHECKBOX_CLASSES = (
        'h-4 w-4 rounded border-slate-300 text-primary-600 '
        'focus:ring-primary-500 focus:ring-offset-0 '
        'dark:border-slate-600 dark:bg-slate-900 dark:checked:bg-primary-500'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_widget_classes()

    def _apply_widget_classes(self):
        for name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get('class', '').strip()

            if isinstance(widget, forms.Textarea):
                base = self.TEXTAREA_CLASSES
            elif isinstance(widget, forms.CheckboxInput):
                base = self.CHECKBOX_CLASSES
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                base = self.SELECT_CLASSES
            elif isinstance(
                widget,
                (forms.TextInput, forms.EmailInput, forms.PasswordInput,
                 forms.NumberInput, forms.URLInput, forms.DateInput,
                 forms.DateTimeInput, forms.TimeInput, forms.SearchInput),
            ):
                base = self.INPUT_CLASSES
            else:
                continue

            widget.attrs['class'] = f'{base} {existing}'.strip()

            # Mobile-optimised keyboards
            if isinstance(widget, forms.NumberInput):
                widget.attrs.setdefault('inputmode', 'decimal')
            elif isinstance(widget, forms.EmailInput):
                widget.attrs.setdefault('inputmode', 'email')
            elif isinstance(widget, forms.DateInput):
                widget.attrs.setdefault('inputmode', 'numeric')

            # Accessibility: link help text to input
            if field.help_text:
                widget.attrs.setdefault('aria-describedby', f'{name}_help')

            if field.required:
                widget.attrs.setdefault('required', True)