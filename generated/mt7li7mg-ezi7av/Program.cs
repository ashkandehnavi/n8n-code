using app_mt7li7mg_ezi7av.Models;
using app_mt7li7mg_ezi7av.Services;

namespace app_mt7li7mg_ezi7av;

internal static class Program
{
    private static readonly TaskManager TaskManager = new();

    private static void Main()
    {
        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.WriteLine("=== برنامه مدیریت وظایف ===");

        var hasUserInput = false;

        while (true)
        {
            ShowMenu();
            var choice = ReadLineOrNull("انتخاب شما: ");

            if (choice is null)
            {
                if (!hasUserInput)
                {
                    RunSampleScenario();
                }
                else
                {
                    Console.WriteLine("\nپایان ورودی دریافت شد. برنامه خاتمه یافت.");
                }

                return;
            }

            hasUserInput = true;
            Console.WriteLine();

            switch (choice.Trim())
            {
                case "1":
                    AddTask();
                    break;
                case "2":
                    ShowTasks(TaskManager.GetAll());
                    break;
                case "3":
                    ShowTasks(TaskManager.GetOpenTasks());
                    break;
                case "4":
                    CompleteTask();
                    break;
                case "5":
                    DeleteTask();
                    break;
                case "0":
                case "6":
                    Console.WriteLine("با موفقیت خارج شدید. خداحافظ!");
                    return;
                default:
                    Console.WriteLine("گزینه نامعتبر است. لطفاً یکی از گزینه‌های منو را انتخاب کنید.");
                    break;
            }

            Console.WriteLine();
        }
    }

    private static void ShowMenu()
    {
        Console.WriteLine("\n--- منوی اصلی ---");
        Console.WriteLine("1) افزودن وظیفه");
        Console.WriteLine("2) نمایش همه وظایف");
        Console.WriteLine("3) نمایش وظایف باز");
        Console.WriteLine("4) تکمیل وظیفه");
        Console.WriteLine("5) حذف وظیفه");
        Console.WriteLine("0) خروج");
    }

    private static void AddTask()
    {
        var title = ReadLineOrNull("عنوان وظیفه: ");
        if (title is null)
        {
            Console.WriteLine("پایان ورودی دریافت شد.");
            return;
        }

        title = title.Trim();
        if (title.Length == 0)
        {
            Console.WriteLine("عنوان وظیفه نمی‌تواند خالی باشد.");
            return;
        }

        var description = ReadLineOrNull("توضیحات (اختیاری): ") ?? string.Empty;
        var task = TaskManager.Add(title, description.Trim());
        Console.WriteLine($"وظیفه با شناسه {task.Id} اضافه شد.");
    }

    private static void CompleteTask()
    {
        var id = ReadId("شناسه وظیفه برای تکمیل: ");
        if (id is null)
        {
            return;
        }

        Console.WriteLine(TaskManager.Complete(id.Value)
            ? "وظیفه با موفقیت تکمیل شد."
            : "وظیفه‌ای با این شناسه پیدا نشد یا قبلاً تکمیل شده است.");
    }

    private static void DeleteTask()
    {
        var id = ReadId("شناسه وظیفه برای حذف: ");
        if (id is null)
        {
            return;
        }

        Console.WriteLine(TaskManager.Delete(id.Value)
            ? "وظیفه با موفقیت حذف شد."
            : "وظیفه‌ای با این شناسه پیدا نشد.");
    }

    private static int? ReadId(string prompt)
    {
        var input = ReadLineOrNull(prompt);
        if (input is null)
        {
            Console.WriteLine("پایان ورودی دریافت شد.");
            return null;
        }

        if (!int.TryParse(input.Trim(), out var id) || id <= 0)
        {
            Console.WriteLine("شناسه نامعتبر است. لطفاً یک عدد مثبت وارد کنید.");
            return null;
        }

        return id;
    }

    private static void ShowTasks(IReadOnlyList<TaskItem> tasks)
    {
        if (tasks.Count == 0)
        {
            Console.WriteLine("هیچ وظیفه‌ای برای نمایش وجود ندارد.");
            return;
        }

        foreach (var task in tasks)
        {
            var status = task.IsCompleted ? "تکمیل‌شده" : "باز";
            Console.WriteLine($"[{task.Id}] {task.Title} - وضعیت: {status}");
            if (!string.IsNullOrWhiteSpace(task.Description))
            {
                Console.WriteLine($"    توضیحات: {task.Description}");
            }

            Console.WriteLine($"    زمان ایجاد: {task.CreatedAt:yyyy-MM-dd HH:mm:ss}");
        }
    }

    private static void RunSampleScenario()
    {
        Console.WriteLine("\nورودی تعاملی دریافت نشد؛ اجرای نمونه برنامه:");
        var task = TaskManager.Add("مطالعه", string.Empty);
        Console.WriteLine($"وظیفه با شناسه {task.Id} اضافه شد.");

        Console.WriteLine("\nفهرست وظایف پس از افزودن:");
        ShowTasks(TaskManager.GetAll());

        if (TaskManager.Complete(task.Id))
        {
            Console.WriteLine("وظیفه با موفقیت تکمیل شد.");
        }

        Console.WriteLine("\nفهرست وظایف پس از تکمیل:");
        ShowTasks(TaskManager.GetAll());
        Console.WriteLine("\nپایان ورودی دریافت شد. برنامه خاتمه یافت.");
    }

    private static string? ReadLineOrNull(string prompt)
    {
        Console.Write(prompt);
        return Console.ReadLine();
    }
}
