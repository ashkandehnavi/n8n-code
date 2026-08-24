using System.Globalization;
using System.Text;

Console.OutputEncoding = Encoding.UTF8;

var tasks = new List<TaskItem>();
var nextId = 1;

Console.WriteLine("=== مدیریت وظایف ===");

while (true)
{
    Console.WriteLine();
    Console.WriteLine("1) افزودن وظیفه");
    Console.WriteLine("2) نمایش همه وظایف");
    Console.WriteLine("3) جست‌وجوی وظیفه");
    Console.WriteLine("4) ویرایش وظیفه");
    Console.WriteLine("5) تکمیل وظیفه");
    Console.WriteLine("6) حذف وظیفه");
    Console.WriteLine("0) خروج");
    Console.Write("انتخاب شما: ");

    var choice = Console.ReadLine();
    if (choice is null || string.IsNullOrWhiteSpace(choice) || choice.Trim() == "0")
    {
        Console.WriteLine("خروج از برنامه.");
        break;
    }

    switch (choice.Trim())
    {
        case "1": AddTask(); break;
        case "2": ShowTasks(tasks, "همه وظایف"); break;
        case "3": SearchTasks(); break;
        case "4": EditTask(); break;
        case "5": CompleteTask(); break;
        case "6": DeleteTask(); break;
        default: Console.WriteLine("گزینه نامعتبر است."); break;
    }
}

void AddTask()
{
    var title = ReadRequired("عنوان وظیفه: ");
    if (title is null) return;

    Console.Write("توضیحات (اختیاری): ");
    var description = Console.ReadLine();
    if (description is null) return;

    var priority = ReadPriority();
    if (priority is null) return;

    var dueDate = ReadDueDate();
    if (dueDate is null && WasEndOfInput) return;

    var item = new TaskItem
    {
        Id = nextId++,
        Title = title,
        Description = description.Trim(),
        Priority = priority.Value,
        DueDate = dueDate
    };

    tasks.Add(item);
    Console.WriteLine($"وظیفه با شناسه {item.Id} افزوده شد.");
}

void SearchTasks()
{
    Console.Write("عبارت جست‌وجو: ");
    var term = Console.ReadLine();
    if (term is null) return;

    term = term.Trim();
    if (term.Length == 0)
    {
        Console.WriteLine("عبارت جست‌وجو نمی‌تواند خالی باشد.");
        return;
    }

    var results = tasks.Where(task =>
        task.Title.Contains(term, StringComparison.CurrentCultureIgnoreCase) ||
        task.Description.Contains(term, StringComparison.CurrentCultureIgnoreCase));

    ShowTasks(results, "نتایج جست‌وجو");
}

void EditTask()
{
    var item = FindTask("شناسه وظیفه برای ویرایش: ");
    if (item is null) return;

    var title = ReadRequired("عنوان جدید: ");
    if (title is null) return;

    Console.Write("توضیحات جدید: ");
    var description = Console.ReadLine();
    if (description is null) return;

    var priority = ReadPriority();
    if (priority is null) return;

    var dueDate = ReadDueDate();
    if (dueDate is null && WasEndOfInput) return;

    item.Title = title;
    item.Description = description.Trim();
    item.Priority = priority.Value;
    item.DueDate = dueDate;
    Console.WriteLine("وظیفه با موفقیت ویرایش شد.");
}

void CompleteTask()
{
    var item = FindTask("شناسه وظیفه برای تکمیل: ");
    if (item is null) return;

    if (item.IsCompleted)
    {
        Console.WriteLine("این وظیفه قبلاً تکمیل شده است.");
        return;
    }

    item.IsCompleted = true;
    Console.WriteLine("وظیفه تکمیل شد.");
}

void DeleteTask()
{
    var item = FindTask("شناسه وظیفه برای حذف: ");
    if (item is null) return;

    tasks.Remove(item);
    Console.WriteLine("وظیفه حذف شد.");
}

TaskItem? FindTask(string prompt)
{
    Console.Write(prompt);
    var input = Console.ReadLine();
    if (input is null) return null;

    if (!int.TryParse(input.Trim(), NumberStyles.Integer, CultureInfo.InvariantCulture, out var id))
    {
        Console.WriteLine("شناسه باید عددی باشد.");
        return null;
    }

    var item = tasks.FirstOrDefault(task => task.Id == id);
    if (item is null)
        Console.WriteLine("وظیفه‌ای با این شناسه پیدا نشد.");

    return item;
}

string? ReadRequired(string prompt)
{
    while (true)
    {
        Console.Write(prompt);
        var value = Console.ReadLine();
        if (value is null) return null;

        value = value.Trim();
        if (value.Length > 0) return value;
        Console.WriteLine("عنوان نمی‌تواند خالی باشد.");
    }
}

Priority? ReadPriority()
{
    while (true)
    {
        Console.Write("اولویت (1=کم، 2=متوسط، 3=زیاد): ");
        var input = Console.ReadLine();
        if (input is null) return null;

        switch (input.Trim())
        {
            case "1": return Priority.Low;
            case "2": return Priority.Medium;
            case "3": return Priority.High;
            default: Console.WriteLine("اولویت نامعتبر است."); break;
        }
    }
}

DateTime? ReadDueDate()
{
    while (true)
    {
        Console.Write("تاریخ سررسید (yyyy-MM-dd، اختیاری): ");
        var input = Console.ReadLine();
        if (input is null)
        {
            WasEndOfInput = true;
            return null;
        }

        input = input.Trim();
        if (input.Length == 0) return null;

        if (DateTime.TryParseExact(input, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
            return date;

        Console.WriteLine("تاریخ نامعتبر است. قالب صحیح مانند 2025-12-31 است.");
    }
}

void ShowTasks(IEnumerable<TaskItem> items, string heading)
{
    var list = items.OrderBy(task => task.Id).ToList();
    Console.WriteLine($"\n--- {heading} ---");

    if (list.Count == 0)
    {
        Console.WriteLine("هیچ وظیفه‌ای وجود ندارد.");
        return;
    }

    foreach (var item in list)
    {
        var status = item.IsCompleted ? "تکمیل‌شده" : "باز";
        var due = item.DueDate?.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) ?? "بدون سررسید";
        Console.WriteLine($"[{item.Id}] {item.Title} | وضعیت: {status} | اولویت: {PriorityText(item.Priority)} | سررسید: {due}");
        if (!string.IsNullOrWhiteSpace(item.Description))
            Console.WriteLine($"    توضیحات: {item.Description}");
    }
}

string PriorityText(Priority priority) => priority switch
{
    Priority.Low => "کم",
    Priority.Medium => "متوسط",
    _ => "زیاد"
};

bool WasEndOfInput { get; set; }

class TaskItem
{
    public int Id { get; set; }
    public string Title { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public Priority Priority { get; set; }
    public bool IsCompleted { get; set; }
    public DateTime? DueDate { get; set; }
}

enum Priority
{
    Low,
    Medium,
    High
}
