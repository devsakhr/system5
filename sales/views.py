from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.urls import reverse
from invoices.models import *
from invoices.forms import *

import json

from django.db.models import Q
from django.http import JsonResponse

import json  # لتحويل البيانات إلى تنسيق JSON  



def sales_invoice_list(request):
    """
    عرض قائمة فواتير المبيعات مع إمكانية البحث والتصفية حسب اسم العميل وتاريخ الفاتورة.
    """
    # جلب فواتير المبيعات وترتيبها تنازليًا بحسب تاريخ الفاتورة (الأحدث أولاً)
    invoices = Invoice.objects.filter(invoice_type='sales').order_by('-invoice_date')
 
    context = {
        'invoices': invoices,
        'title': 'قائمة فواتير المبيعات'
    }
    return render(request, 'sales/invoice_list.html', context)




def ajax_search_sales_invoices(request):
    invoice_number = request.GET.get('invoice_number', '').strip()
    customer_name = request.GET.get('customer_name', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # فلترة فواتير المبيعات فقط
    qs = Invoice.objects.filter(invoice_type='sales')

    if invoice_number:
        qs = qs.filter(invoice_number__icontains=invoice_number)

    if customer_name:
        qs = qs.filter(customer__name__icontains=customer_name)

    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(invoice_date__date__gte=date_from)
        except ValueError:
            pass  # إذا كانت صيغة التاريخ غير صحيحة، يمكن تجاهل الفلترة

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(invoice_date__date__lte=date_to)
        except ValueError:
            pass  # إذا كانت صيغة التاريخ غير صحيحة، يمكن تجاهل الفلترة

    # ترتيب تنازلي (الأحدث أولاً)
    qs = qs.order_by('-id')

    data = []
    for invoice in qs:
        data.append({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.invoice_date.strftime('%Y-%m-%d %H:%M'),
            'customer_name': invoice.customer.name if invoice.customer else '—',
            'return_reason': invoice.return_reason if invoice.return_reason else '—',
            'total_amount': str(invoice.total_amount),
        })

    return JsonResponse({'results': data})




def create_sales_invoice(request):
    customer_form = CustomerForm()
    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST, request.FILES)
        formset = InvoiceItemFormSet(request.POST, prefix='items')
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # احفظ الفاتورة مع ربطها بالعميل
                    invoice = form.save(commit=False)
                    invoice.customer = form.cleaned_data['customer']
                    invoice.save()
                    
                    formset.instance = invoice
                    formset.save()
                    
                    # منطق تحديث المخزون (يبقى كما هو)
                    for item_form in formset:
                        if not item_form.cleaned_data.get('DELETE', False):
                            item = item_form.save(commit=False)
                            product = item.product
                            base_quantity = item.quantity
                            
                            #if product.stock < base_quantity:
                            #    raise Exception(f"لا توجد كمية كافية للمنتج {product.name_ar}")
                            product.stock -= int(base_quantity)
                            product.save()

                messages.success(request, 'تم إنشاء فاتورة المبيعات بنجاح.')
                return redirect('invoice_print_view', invoice_id=invoice.id)
            except Exception as e:
                messages.error(request, f'حدث خطأ: {str(e)}')
        else:
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج')
    else:
        form = SalesInvoiceForm()
        formset = InvoiceItemFormSet(prefix='items')
    
    # الباقي يبقى كما هو
    products = Product.objects.all()
    product_prices = {str(product.id): str(product.price) for product in products}
    product_units = {str(product.id): product.unit.abbreviation for product in products}
    conversion_units = {
        str(conv.id): {
            "abbr": conv.larger_unit_name if hasattr(conv, 'larger_unit_name') else conv.conversion_unit,
            "factor": str(conv.conversion_factor)
        }
        for conv in UnitConversion.objects.all()
    }
    context = {
        'customer_form': customer_form,

        'form': form,
        'formset': formset,
        'title': 'إنشاء فاتورة مبيعات - النظام المحاسبي',
        'product_prices': json.dumps(product_prices),
        'product_units': json.dumps(product_units),
        'conversion_units': json.dumps(conversion_units),
    }
    return render(request, 'sales/create_invoice.html', context)




def update_sales_invoice(request, invoice_id):
    """
    دالة عرض لتحديث فاتورة مبيعات موجودة.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id)

    if request.method == 'POST':
        form = SalesInvoiceForm(request.POST, request.FILES, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice, prefix='items')
   #     print("request.POST content:", request.POST.dict())

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    invoice = form.save(commit=False)
                    invoice.customer = form.cleaned_data['customer']
                    invoice.save()

                    # تخزين العناصر القديمة لمقارنة التعديلات
                    old_items = {item.id: item for item in invoice.invoice_items.all()}
                    formset.instance = invoice
                    formset_items = formset.save(commit=False)

                    for item in formset_items:
                        if item.id:
                            old_item = old_items.pop(item.id, None)
                        else:
                            old_item = None

                        product = item.product
                        base_quantity = item.quantity

                        if old_item:
                            # حساب الفرق بين الكمية الجديدة والقديمة
                            quantity_difference = base_quantity - old_item.quantity
                            product.stock -= int(quantity_difference)
                        else:
                            if product.stock < base_quantity:
                                raise Exception(f"لا توجد كمية كافية للمنتج {product.name_ar}")
                            product.stock -= int(base_quantity)

                        if product.stock < 0:
                            raise Exception(f"الكمية في المخزون للمنتج {product.name_ar} أصبحت أقل من صفر.")

                        item.save()
                        product.save()

                    # استعادة المخزون للعناصر التي تم حذفها
                 #   for old_item in old_items.values():
                 #       product = old_item.product
                 #       product.stock += int(old_item.quantity)
                 #       product.save()
                  #      old_item.delete()

                    invoice.calculate_totals()
                    invoice.save()

                    messages.success(request, 'تم تحديث فاتورة المبيعات بنجاح.')
                    return redirect('sales_invoice_detail', invoice_id=invoice.id)

            except Exception as e:
                messages.error(request, f'حدث خطأ أثناء تحديث الفاتورة: {str(e)}')
        else:
            print("Formset Errors:", formset.errors)
            messages.error(request, 'يرجى تصحيح الأخطاء في النموذج.')
    else:
        form = SalesInvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice, prefix='items')

    products = Product.objects.all()
    product_prices = {str(product.id): str(product.price) for product in products}
    product_units = {str(product.id): product.unit.abbreviation for product in products}
    conversion_units = {
        str(conv.id): {
            "abbr": conv.larger_unit_name if hasattr(conv, 'larger_unit_name') else conv.conversion_unit,
            "factor": str(conv.conversion_factor)
        }
        for conv in UnitConversion.objects.all()
    }
    context = {
        'form': form,
        'formset': formset,
        'title': 'تحديث فاتورة مبيعات - النظام المحاسبي',
        'invoice_id': invoice_id,
        'product_prices': json.dumps(product_prices),
        'product_units': json.dumps(product_units),
        'conversion_units': json.dumps(conversion_units),
    }
    return render(request, 'sales/edit_invoice.html', context)



from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def add_customer(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            return JsonResponse({
                'success': True,
                'customer_id': customer.id,
                'customer_name': customer.name
            })
        else:
            return JsonResponse({
                'success': False,
                'errors': form.errors.as_json()
            })
    return JsonResponse({'success': False, 'errors': 'Invalid request method'})




def delete_sales_invoice(request, invoice_id):
    """
    دالة لحذف فاتورة مبيعات.
    يتم التأكد من أن الفاتورة من نوع 'sales'.
    عند تأكيد الحذف (POST)، يتم حذف الفاتورة وإعادة التوجيه إلى صفحة قائمة فواتير المبيعات.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, invoice_type='sales')
    
    if request.method == 'POST':
        invoice.delete()
        messages.success(request, "تم حذف فاتورة المبيعات بنجاح.")
        return redirect('sales_invoice_list')  # تأكد من وجود مسار URL مناسب لقائمة فواتير المبيعات






def sales_invoice_detail(request, invoice_id):

    invoice = get_object_or_404(Invoice, id=invoice_id, invoice_type='sales')
    context = {
        'invoice': invoice,
        'invoice_items': invoice.invoice_items.all(),  # أو الاستعلام المناسب
        'title': f'تفاصيل فاتورة المبيعات {invoice.invoice_number}'
    }
    return render(request, 'sales/invoice_detail.html', context)














from django.http import JsonResponse
from datetime import datetime

def list_sales_returns(request):
    context = {
        'title': 'قائمة مرتجعات المبيعات (بحث ديناميكي)',
    }
    return render(request, 'sales_returns/list.html', context)

def ajax_search_sales_returns(request):
    invoice_number = request.GET.get('invoice_number', '').strip()
    customer_name = request.GET.get('customer_name', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # فلترة فواتير المرتجع فقط
    qs = Invoice.objects.filter(invoice_type='sales_return')

    if invoice_number:
        qs = qs.filter(invoice_number__icontains=invoice_number)

    if customer_name:
        qs = qs.filter(customer__name__icontains=customer_name)

    if date_from:
        try:
            date_from = datetime.strptime(date_from, '%Y-%m-%d').date()
            qs = qs.filter(invoice_date__date__gte=date_from)
        except ValueError:
            pass  # إذا كانت صيغة التاريخ غير صحيحة، يمكن تجاهل الفلترة

    if date_to:
        try:
            date_to = datetime.strptime(date_to, '%Y-%m-%d').date()
            qs = qs.filter(invoice_date__date__lte=date_to)
        except ValueError:
            pass  # إذا كانت صيغة التاريخ غير صحيحة، يمكن تجاهل الفلترة

    # ترتيب تنازلي (الأحدث أولاً)
    qs = qs.order_by('-id')

    data = []
    for invoice in qs:
        data.append({
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.invoice_date.strftime('%Y-%m-%d %H:%M'),
            'customer_name': invoice.customer.name if invoice.customer else '—',
            'return_reason': invoice.return_reason if invoice.return_reason else '—',
            'total_amount': str(invoice.total_amount),
        })

    return JsonResponse({'results': data})





def delete_sales_return_invoice(request, invoice_id):
    """
    دالة لحذف فاتورة مبيعات.
    يتم التأكد من أن الفاتورة من نوع 'sales'.
    عند تأكيد الحذف (POST)، يتم حذف الفاتورة وإعادة التوجيه إلى صفحة قائمة فواتير المبيعات.
    """
    invoice = get_object_or_404(Invoice, id=invoice_id, invoice_type='sales_return')
    
    if request.method == 'POST':
        invoice.delete()
        messages.success(request, "تم حذف فاتورة المبيعات بنجاح.")
        return redirect('list_sales_returns')  # تأكد من وجود مسار URL مناسب لقائمة فواتير المبيعات



def sales_return_invoice_detail(request, invoice_id):

    invoice = get_object_or_404(Invoice, id=invoice_id, invoice_type='sales_return')
    context = {
        'invoice': invoice,
        'invoice_items': invoice.invoice_items.all(),
        'title': f'تفاصيل فاتورة مرتجع المبيعات {invoice.invoice_number}'
    }
    return render(request, 'sales_returns/invoice_detail.html', context)











import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404




from .forms import *


def update_sales_return_invoice(request, invoice_id):

    SalesReturnInvoiceItemInlineFormSet = inlineformset_factory(
        Invoice,
        InvoiceItem,
        form=SalesReturnInvoiceItemForm,
        formset=SalesReturnInvoiceItemFormSet,
        extra=0,
        can_delete=False
    )
    invoice = get_object_or_404(Invoice, pk=invoice_id, invoice_type='sales_return')
    
    if request.method == 'POST':
        form = SalesReturnInvoiceForm(request.POST, request.FILES, instance=invoice)
        formset = SalesReturnInvoiceItemInlineFormSet(request.POST, request.FILES, instance=invoice)
        
        if form.is_valid() and formset.is_valid():
            invoice = form.save(commit=False)
            invoice.invoice_type = 'sales_return'
            invoice.save()  # حفظ التحديثات على الفاتورة
            
            # إعادة حساب الإجماليات بعد التحديث
            invoice.calculate_totals()
            
            # ربط formset بالفاتورة المحفوظة
            formset.instance = invoice
            formset.save()
            
            return redirect(reverse('sales_return_invoice_detail', kwargs={'invoice_id': invoice.id}))
        
        # في حالة وجود أخطاء في التحقق نعيد عرض النموذج مع الأخطاء
        return render(request, 'sales_returns/edit_sales_return.html', {
            'form': form,
            'formset': formset
        })
    
    # معالجة طلب GET: إنشاء الفورم مع instance الحالي
    form = SalesReturnInvoiceForm(instance=invoice)
    form.fields['original_invoice'].widget.attrs.update({'disabled': 'disabled'})
    form.fields['customer'].widget.attrs.update({'disabled': 'disabled'})
    formset = SalesReturnInvoiceItemInlineFormSet(instance=invoice)
    
    return render(request, 'sales_returns/edit_sales_return.html', {
        'form': form,
        'formset': formset
    })






from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.db import transaction
from django.contrib import messages
from django.urls import reverse

from invoices.models import Invoice, Product
from .forms import *
from django.shortcuts import get_object_or_404, render, redirect
from django.db import transaction
from django.contrib import messages
from invoices.models import Invoice, InvoiceItem, Product
from .forms import SalesReturnInvoiceForm, SalesReturnInvoiceItemFormSet



from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from invoices.models import Invoice, InvoiceItem, Product
from .forms import SalesReturnInvoiceForm, SalesReturnInvoiceItemInlineFormSet

from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.contrib import messages
from invoices.models import Invoice, InvoiceItem, Product
from .forms import SalesReturnInvoiceForm, SalesReturnInvoiceItemInlineFormSet

def create_sales_return_invoice(request, original_id=None):
    original_invoice = None
    return_invoice = None

    if original_id:
        original_invoice = get_object_or_404(
            Invoice,
            id=original_id,
            invoice_type='sales'
        )
        return_invoice = Invoice.objects.filter(
            original_invoice=original_invoice,
            invoice_type='sales_return'
        ).first()

    # إذا لم توجد فاتورة مرتجع، نقوم بإنشاء كائن فاتورة جديد مع ربطها بالفاتورة الأصلية
    if not return_invoice:
        parent_invoice = Invoice(original_invoice=original_invoice)
    else:
        parent_invoice = return_invoice

    if request.method == 'POST':
     
        form = SalesReturnInvoiceForm(request.POST, request.FILES, instance=parent_invoice)

        # استخدام الفئة الناتجة من inlineformset_factory
        formset = SalesReturnInvoiceItemInlineFormSet(
            request.POST,
            request.FILES,
            instance=parent_invoice
        )

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    invoice = form.save(commit=False)

                    if not return_invoice:
                        invoice.invoice_type = 'sales_return'
                        invoice.created_by = request.user
                        invoice.original_invoice = original_invoice
                        invoice.customer = original_invoice.customer

                    if not invoice.invoice_number:
                        invoice.invoice_number = invoice.generate_invoice_number()

                    invoice.save()

                    # تحديث instance الخاص بالفومسيت إلى الفاتورة المحفوظة
                    formset.instance = invoice
                    instances = formset.save(commit=False)
                    stock_updates = {}

                    for item in instances:
                        # معالجة البنود التي تحتوي على كمية أكبر من 0 فقط
                        if item.quantity > 0:
                            original_item = original_invoice.invoice_items.filter(
                                product=item.product
                            ).first()

                            if original_item and item.quantity > original_item.quantity:
                                messages.error(
                                    request,
                                    f'🚨 الكمية المدخلة ({item.quantity}) للمنتج "{item.product.name_ar}" '
                                    f'تتجاوز الكمية المباعة الأصلية ({original_item.quantity}).'
                                )
                                return redirect('create_sales_return_invoice', original_id=original_id)

                            stock_updates[item.product.id] = stock_updates.get(item.product.id, 0) + item.quantity
                            item.invoice = invoice
                            item.save()
                        else:
                            if item.id:  # في حالة التعديل وحذف بند موجود (عند تعيين الكمية إلى 0)
                                formset.deleted_objects.append(item)

                    for obj in formset.deleted_objects:
                        obj.delete()

                    if 'finalize' in request.POST:
                        if not invoice.invoice_items.exists():
                            messages.error(request, '🚨 لا يمكن إتمام الفاتورة بدون عناصر.')
                            return redirect('create_sales_return_invoice', original_id=original_id)

                        for product_id, qty in stock_updates.items():
                            product = Product.objects.get(id=product_id)
                            product.stock += qty
                            product.save()

                        invoice.status = 'completed'
                        invoice.save()
                        messages.success(request, '✅ تم إتمام الفاتورة وتحديث المخزون بنجاح.')
                        return redirect('invoice_print_view', invoice_id=invoice.id)

                    messages.success(request, '✅ تم حفظ الفاتورة كمسودة بنجاح.')
                    return redirect('create_sales_return_invoice', original_id=original_id)

            except Exception as e:
                messages.error(request, f'❌ حدث خطأ أثناء الحفظ: {str(e)}')

        else:
            print("🔴 أخطاء النموذج الرئيسي:", form.errors)
            print("🔴 أخطاء نموذج البنود:", formset.errors)

            error_messages = []

            # أخطاء نموذج الفاتورة الرئيسي
            for field, errors_list in form.errors.items():
                for error_msg in errors_list:
                    if field == '__all__':
                        # خطأ عام (non-field error)
                        error_messages.append(f"❌ خطأ عام في الفاتورة: {error_msg}")
                    else:
                        label = form.fields[field].label if field in form.fields else field
                        error_messages.append(f"❌ {label}: {error_msg}")

            # أخطاء نماذج البنود (FormSet)
            for i, f_form in enumerate(formset.forms):
                if f_form.errors:
                    for field, errors_list in f_form.errors.items():
                        for error_msg in errors_list:
                            if field == '__all__':
                                error_messages.append(f"❌ بند #{i + 1} - خطأ عام: {error_msg}")
                            else:
                                label = f_form.fields[field].label if field in f_form.fields else field
                                error_messages.append(f"❌ بند #{i + 1} - {label}: {error_msg}")

            messages.error(request, 'يرجى تصحيح الأخطاء التالية: ' + ' | '.join(error_messages))
    else:
        initial = {}
        if original_invoice:
            
            initial = {
                'original_invoice': original_invoice,  # استخدام الفاتورة الأصلية مباشرةً
                'customer': original_invoice.customer,
                'payment_method': original_invoice.payment_method,
                'discount_percentage': original_invoice.discount_percentage,
                'notes': f"🚀 مرتجع فاتورة #{original_invoice.invoice_number}"
            }

        form = SalesReturnInvoiceForm(instance=return_invoice, initial=initial)
        formset = SalesReturnInvoiceItemInlineFormSet(
            instance=return_invoice if return_invoice else Invoice(original_invoice=original_invoice)
        )
        form.fields['original_invoice'].widget.attrs.update({'disabled': 'disabled'})
        form.fields['customer'].widget.attrs.update({'disabled': 'disabled'})

    
    if return_invoice:
        # في حالة تعديل فاتورة مرتجع موجودة، فلنعرض كل فواتير المبيعات (أو الفاتورة الأصلية فقط، حسب رغبتك)
        sales_invoices = Invoice.objects.filter(invoice_type='sales')
        # أو يمكنك اختيار:
        # sales_invoices = Invoice.objects.filter(id=original_invoice.id)
    else:
        # في حالة إنشاء فاتورة مرتجع جديدة، استبعد أي فاتورة مبيعات لها فاتورة مرتجع
        sales_invoices = Invoice.objects.filter(invoice_type='sales').exclude(
            id__in=Invoice.objects.filter(invoice_type='sales_return').values_list('original_invoice_id', flat=True)
        )

    context = {
        'form': form,
        'formset': formset,
        'original_invoice': original_invoice,
        'sales_invoices': sales_invoices,
    #    'sales_invoices': Invoice.objects.filter(invoice_type='sales'),
        'return_invoice': return_invoice,
        'page_title': '📌 إنشاء فاتورة مرتجع مبيعات' if not return_invoice else '📌 تعديل فاتورة مرتجع',
        'template_name': 'sales_return_invoice_form4.html'
    }

    return render(request, 'sales_return_invoice_form4.html', context)
