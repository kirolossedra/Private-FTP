#import <UIKit/UIKit.h>
#import "WhiteRaccoon.h"

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

@interface ViewController : UIViewController <WRRequestDelegate, UITableViewDataSource, UITableViewDelegate>
@property (strong, nonatomic) UITextField *hostField;
@property (strong, nonatomic) UITextField *userField;
@property (strong, nonatomic) UITextField *passwordField;
@property (strong, nonatomic) UIButton *downloadButton;
@property (strong, nonatomic) UIButton *validateButton;
@property (strong, nonatomic) UIButton *addScheduleButton;
@property (strong, nonatomic) UITableView *scheduleTable;
@property (strong, nonatomic) UIImageView *imageView;
@property (strong, nonatomic) UIProgressView *progressBar;

@property (strong, nonatomic) WRRequestDownload *currentDownload;
@property (strong, nonatomic) NSMutableArray<NSDateComponents *> *scheduleList;
@property (strong, nonatomic) NSTimer *clockTimer;
@property (assign, nonatomic) BOOL recentlyTriggered;
@property (assign, nonatomic) unsigned long long totalBytesReceived;

// Picker overlay
@property (strong, nonatomic) UIView *pickerContainer;
@property (strong, nonatomic) UIDatePicker *timePicker;
@end


@implementation AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    self.window = [[UIWindow alloc] initWithFrame:[[UIScreen mainScreen] bounds]];
    self.window.backgroundColor = [UIColor whiteColor];
    ViewController *vc = [[ViewController alloc] init];
    self.window.rootViewController = vc;
    [self.window makeKeyAndVisible];
    return YES;
}
@end


@implementation ViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = [UIColor whiteColor];
    CGFloat width = self.view.bounds.size.width - 40;
    CGFloat y = 80;

    self.hostField = [[UITextField alloc] initWithFrame:CGRectMake(20, y, width, 40)];
    self.hostField.placeholder = @"Host (e.g. 192.168.1.10)";
    self.hostField.text = @"192.168.0.138";
    self.hostField.borderStyle = UITextBorderStyleRoundedRect;
    [self.view addSubview:self.hostField];   y += 60;

    self.userField = [[UITextField alloc] initWithFrame:CGRectMake(20, y, width, 40)];
    self.userField.placeholder = @"User";
    self.userField.text = @"user";
    self.userField.borderStyle = UITextBorderStyleRoundedRect;
    [self.view addSubview:self.userField];   y += 60;

    self.passwordField = [[UITextField alloc] initWithFrame:CGRectMake(20, y, width, 40)];
    self.passwordField.placeholder = @"Password";
    self.passwordField.text = @"pass";
    self.passwordField.borderStyle = UITextBorderStyleRoundedRect;
    self.passwordField.secureTextEntry = YES;
    [self.view addSubview:self.passwordField];  y += 60;

    self.downloadButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.downloadButton.frame = CGRectMake(20, y, width, 44);
    [self.downloadButton setTitle:@"Download Now" forState:UIControlStateNormal];
    self.downloadButton.backgroundColor = [UIColor systemBlueColor];
    [self.downloadButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    self.downloadButton.layer.cornerRadius = 8;
    [self.downloadButton addTarget:self action:@selector(downloadTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.downloadButton]; y += 60;

    self.validateButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.validateButton.frame = CGRectMake(20, y, width, 44);
    [self.validateButton setTitle:@"Validate" forState:UIControlStateNormal];
    self.validateButton.backgroundColor = [UIColor systemGreenColor];
    [self.validateButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    self.validateButton.layer.cornerRadius = 8;
    [self.validateButton addTarget:self action:@selector(validateTapped) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.validateButton]; y += 60;

    self.addScheduleButton = [UIButton buttonWithType:UIButtonTypeSystem];
    self.addScheduleButton.frame = CGRectMake(20, y, width, 44);
    [self.addScheduleButton setTitle:@"Add Schedule Time" forState:UIControlStateNormal];
    self.addScheduleButton.backgroundColor = [UIColor systemOrangeColor];
    [self.addScheduleButton setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    self.addScheduleButton.layer.cornerRadius = 8;
    [self.addScheduleButton addTarget:self action:@selector(showTimePicker) forControlEvents:UIControlEventTouchUpInside];
    [self.view addSubview:self.addScheduleButton]; y += 60;

    self.scheduleTable = [[UITableView alloc] initWithFrame:CGRectMake(20, y, width, 150)
                                                      style:UITableViewStylePlain];
    self.scheduleTable.dataSource = self;
    self.scheduleTable.delegate = self;
    self.scheduleTable.layer.borderColor = [UIColor lightGrayColor].CGColor;
    self.scheduleTable.layer.borderWidth = 1;
    self.scheduleTable.layer.cornerRadius = 8;
    [self.view addSubview:self.scheduleTable]; y += 170;

    self.progressBar = [[UIProgressView alloc] initWithFrame:CGRectMake(20, y, width, 20)];
    self.progressBar.progressViewStyle = UIProgressViewStyleDefault;
    self.progressBar.progress = 0.0;
    self.progressBar.hidden = YES;
    [self.view addSubview:self.progressBar]; y += 30;

    self.imageView = [[UIImageView alloc] initWithFrame:CGRectMake(20, y, width, 130)];
    self.imageView.contentMode = UIViewContentModeScaleAspectFit;
    self.imageView.backgroundColor = [UIColor colorWithWhite:0.95 alpha:1];
    [self.view addSubview:self.imageView];

    self.scheduleList = [NSMutableArray array];
    self.clockTimer = [NSTimer scheduledTimerWithTimeInterval:60.0
                                                       target:self
                                                     selector:@selector(checkScheduleTick)
                                                     userInfo:nil
                                                      repeats:YES];

    [self setupPicker];
}

#pragma mark - Picker Setup

- (void)setupPicker {
    CGFloat height = 300;
    self.pickerContainer = [[UIView alloc] initWithFrame:CGRectMake(0, self.view.frame.size.height, self.view.frame.size.width, height)];
    self.pickerContainer.backgroundColor = [UIColor secondarySystemBackgroundColor];

    UIToolbar *toolbar = [[UIToolbar alloc] initWithFrame:CGRectMake(0, 0, self.view.frame.size.width, 44)];
    UIBarButtonItem *cancel = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemCancel
                                                                            target:self
                                                                            action:@selector(hideTimePicker)];
    UIBarButtonItem *flex = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace
                                                                          target:nil
                                                                          action:nil];
    UIBarButtonItem *done = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemAdd
                                                                          target:self
                                                                          action:@selector(addSelectedTime)];
    [toolbar setItems:@[cancel, flex, done]];

    self.timePicker = [[UIDatePicker alloc] initWithFrame:CGRectMake(0, 44, self.view.frame.size.width, height - 44)];
    self.timePicker.datePickerMode = UIDatePickerModeTime;
    self.timePicker.preferredDatePickerStyle = UIDatePickerStyleWheels;

    [self.pickerContainer addSubview:toolbar];
    [self.pickerContainer addSubview:self.timePicker];
    [self.view addSubview:self.pickerContainer];
}

- (void)showTimePicker {
    [UIView animateWithDuration:0.3 animations:^{
        CGRect f = self.pickerContainer.frame;
        f.origin.y = self.view.frame.size.height - f.size.height;
        self.pickerContainer.frame = f;
    }];
}

- (void)hideTimePicker {
    [UIView animateWithDuration:0.3 animations:^{
        CGRect f = self.pickerContainer.frame;
        f.origin.y = self.view.frame.size.height;
        self.pickerContainer.frame = f;
    }];
}

- (void)addSelectedTime {
    NSDateComponents *comp = [[NSCalendar currentCalendar]
                              components:(NSCalendarUnitHour|NSCalendarUnitMinute)
                              fromDate:self.timePicker.date];
    [self.scheduleList addObject:comp];
    [self.scheduleTable reloadData];
    [self hideTimePicker];
}

#pragma mark - FTP Actions

- (void)validateTapped {
    NSString *message = [NSString stringWithFormat:@"Host: %@\nUser: %@\nPassword: %@",
                         self.hostField.text,
                         self.userField.text,
                         self.passwordField.text];
    [self showAlertWithTitle:@"Entered Information" message:message];
}

- (void)downloadTapped {
    [self startDownload];
}

- (void)startDownload {
    NSString *host = self.hostField.text;
    NSString *user = self.userField.text;
    NSString *pass = self.passwordField.text;

    if (host.length == 0) {
        [self showAlertWithTitle:@"Error" message:@"Please enter a host."];
        return;
    }

    self.progressBar.hidden = NO;
    self.progressBar.progress = 0.0;
    self.totalBytesReceived = 0;

    NSString *hostWithPort = [NSString stringWithFormat:@"%@:2121", host];
    self.currentDownload = [[WRRequestDownload alloc] init];
    self.currentDownload.delegate = self;
    self.currentDownload.hostname = hostWithPort;
    self.currentDownload.username = user.length ? user : nil;
    self.currentDownload.password = pass.length ? pass : nil;
    self.currentDownload.path = @"/download";

    [self.currentDownload start];
}

#pragma mark - WRRequestDelegate

- (void)requestDataAvailable:(WRRequestDownload *)request {
    // Pure network transaction — discard data immediately
    NSUInteger bytesChunk = request.receivedData.length;
    self.totalBytesReceived += bytesChunk;

    // Discard to prevent RAM growth
    request.receivedData = [NSMutableData data];

    // Simulate light progress indicator (optional visual cue)
    float simulated = fmodf((float)(self.totalBytesReceived % 1000000) / 1000000.0f, 1.0);
    dispatch_async(dispatch_get_main_queue(), ^{
        self.progressBar.progress = simulated;
    });

    NSLog(@"Network chunk received (%lu bytes) — total %llu", (unsigned long)bytesChunk, self.totalBytesReceived);
}

- (void)requestCompleted:(WRRequest *)request {
    self.progressBar.progress = 1.0;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        self.progressBar.hidden = YES;
    });

    NSString *msg = [NSString stringWithFormat:@"FTP transaction complete.\nTotal network bytes: %llu", self.totalBytesReceived];
    [self showAlertWithTitle:@"Network Transfer Done" message:msg];
}

- (void)requestFailed:(WRRequest *)request {
    self.progressBar.hidden = YES;
    NSString *err = [NSString stringWithFormat:@"FTP transaction failed.\n%@", request.error.message];
    [self showAlertWithTitle:@"Transfer Failed" message:err];
}

- (BOOL)shouldOverwriteFile:(WRRequest *)request { return YES; }

#pragma mark - Schedule Tick

- (void)checkScheduleTick {
    NSDateComponents *nowComp = [[NSCalendar currentCalendar]
                                 components:(NSCalendarUnitHour|NSCalendarUnitMinute)
                                 fromDate:[NSDate date]];

    for (NSDateComponents *comp in self.scheduleList) {
        if (comp.hour == nowComp.hour && comp.minute == nowComp.minute) {
            if (!self.recentlyTriggered) {
                self.recentlyTriggered = YES;
                [self startDownload];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(65 * NSEC_PER_SEC)),
                               dispatch_get_main_queue(), ^{
                    self.recentlyTriggered = NO;
                });
            }
        }
    }
}

#pragma mark - TableView

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return self.scheduleList.count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    static NSString *cid = @"c";
    UITableViewCell *cell = [tableView dequeueReusableCellWithIdentifier:cid];
    if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:cid];
    NSDateComponents *c = self.scheduleList[indexPath.row];
    cell.textLabel.text = [NSString stringWithFormat:@"%02ld:%02ld", (long)c.hour, (long)c.minute];
    return cell;
}

- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)editingStyle
 forRowAtIndexPath:(NSIndexPath *)indexPath {
    if (editingStyle == UITableViewCellEditingStyleDelete) {
        [self.scheduleList removeObjectAtIndex:indexPath.row];
        [self.scheduleTable reloadData];
    }
}

#pragma mark - Helper

- (void)showAlertWithTitle:(NSString *)title message:(NSString *)message {
    UIAlertController *a = [UIAlertController alertControllerWithTitle:title
                                                               message:message
                                                        preferredStyle:UIAlertControllerStyleAlert];
    [a addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [self presentViewController:a animated:YES completion:nil];
}

@end


int main(int argc, char * argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
